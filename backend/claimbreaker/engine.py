import asyncio
import hashlib
import json
import os
import base64
import time
from pathlib import Path
from datetime import timedelta
from sqlalchemy import select, delete
from .db import Session, Case, Artifact, Job, Execution, Event, emit, utcnow, uid, utc_iso
from .config import settings
from . import storage
from .parsing import parse
from .checks import (
    extract_claims,
    locate,
    stable,
    metric_name,
    compare_metrics,
    paper_internal,
    methodology,
    graph_for,
    finding,
)
from .providers import ModelProvider
from .schemas import ExtractedClaim
from .execution import execution_plan, execution_questions, run_isolated, runner_status, terminate
from .additional_checks import arithmetic_checks
from .protocol_checks import protocol_checks
from .parser_process import parse_bounded, PARSER_FINGERPRINT
from .claim_validation import merge_claims
from .run_checks import execution_checks, paper_execution_checks
from .discovery import prioritize
from .review import retain_reviews
from .research_checks import expanded_checks
from .ocr import recover_pages, verification_questions, gate_ocr
from .paper_checks import extended_paper_checks
from .scientific_agent import investigate, apply_interpretations

RUNNING = {}
PROVIDERS = {}
TIMINGS = {}
STOP_EVENT = None


async def cancel_analysis(case_id):
    task = RUNNING.get(case_id)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), 15)
        except (asyncio.CancelledError, TimeoutError):
            pass
    await terminate(case_id)


async def expire_cases():
    with Session() as db:
        expired = list(
            db.scalars(
                select(Case).where(
                    Case.created_at < utcnow() - timedelta(days=settings().retention_days)
                )
            )
        )
        for case in expired:
            if case.id in RUNNING:
                continue
            try:
                for a in db.scalars(select(Artifact).where(Artifact.case_id == case.id)):
                    await asyncio.to_thread(storage.delete, a.storage_key)
                db.delete(case)
                db.commit()
            except Exception:
                db.rollback()  # Retry a failed private-storage deletion on the next sweep.


def artifact_dict(a):
    return {
        "id": a.id,
        "path": a.path,
        "kind": a.kind,
        "size": a.size,
        "sha256": a.sha256,
        "parsed": a.parsed or {},
    }


def execution_dict(e):
    return {
        "id": e.id,
        "status": e.status,
        "manifest": e.manifest,
        "output": e.output,
        "created_at": utc_iso(e.created_at),
    }


def save(db, case, job, result, stage, message):
    db.refresh(job)
    if job.state == "cancelled":
        raise asyncio.CancelledError()
    if job.id in PROVIDERS:
        provider = PROVIDERS[job.id]
        result["_provider_budget"] = {"steps": provider.steps, "input_chars": provider.input_chars}
    if job.id in TIMINGS:
        started, elapsed = TIMINGS[job.id]
        result["_elapsed_seconds"] = round(elapsed + time.monotonic() - started, 3)
    case.result = json.loads(json.dumps(result, allow_nan=False))
    case.status = stage
    case.updated_at = utcnow()
    job.checkpoint = stage
    db.commit()
    emit(db, case.id, stage, message)


async def analyze(job_id):
    with Session() as db:
        job = db.get(Job, job_id)
        if not job:
            return
        case = db.get(Case, job.case_id)
        if not case:
            return
        old_result = case.result or {}
        result = {
            "claims": [],
            "findings": [],
            "checks": [],
            "questions": [],
            "executions": [],
            "warnings": [],
            "agent_actions": [],
            "provider": "deterministic",
            "coverage": {},
            "history": old_result.get("history", []),
            "_resume_count": old_result.get("_resume_count", 0),
            "_provider_budget": old_result.get("_provider_budget", {}),
        }
        if old_result.get("findings") and old_result.get("_revision") != case.revision:
            result["history"] = (
                result["history"]
                + [
                    {
                        "revision": old_result.get("_revision", max(0, case.revision - 1)),
                        "at": utcnow().isoformat(),
                        "findings": [{**f, "superseded": True} for f in old_result["findings"]],
                        "coverage": old_result.get("coverage", {}),
                    }
                ]
            )[-10:]
        provider = ModelProvider(case.provider)
        provider.primary_paper = next(
            (d["answer"] for d in reversed(case.decisions) if d["question_id"] == "primary-paper"),
            None,
        )
        result["_revision"] = case.revision
        provider.steps = old_result.get("_provider_budget", {}).get("steps", 0)
        provider.input_chars = old_result.get("_provider_budget", {}).get("input_chars", 0)
        PROVIDERS[job.id] = provider

        def persist_model_budget():
            db.refresh(job)
            if job.state == "cancelled":
                raise asyncio.CancelledError()
            snapshot = dict(case.result or {})
            snapshot["_provider_budget"] = {
                "steps": provider.steps,
                "input_chars": provider.input_chars,
            }
            case.result = snapshot
            db.commit()

        provider.on_step = persist_model_budget
        try:
            for source in case.sources:
                result["warnings"].extend(
                    paper.get("reason", "Linked paper unavailable; upload its PDF")
                    for paper in source.get("linked_papers", [])
                    if paper["status"] != "acquired"
                )
            artifacts = list(
                db.scalars(
                    select(Artifact).where(Artifact.case_id == case.id).order_by(Artifact.path)
                )
            )
            if not artifacts:
                raise ValueError("Add a project ZIP, repository, or paper before starting")
            explicit_papers = [
                a
                for a in artifacts
                if any(
                    s.get("type") == "upload"
                    and s.get("name") == a.path
                    and a.path.lower().endswith(".pdf")
                    for s in case.sources
                )
            ]
            if not provider.primary_paper and len(explicit_papers) == 1:
                provider.primary_paper = explicit_papers[0].id
            result["discovery"] = {
                "primary_paper_id": provider.primary_paper,
                "basis": "Researcher choice or sole separately uploaded PDF; repository figures retain their source roles"
                if provider.primary_paper
                else "No unique explicit paper; inspect candidate choices",
            }
            save(
                db,
                case,
                job,
                result,
                "inspecting",
                f"Inspecting {len(artifacts)} immutable source artifacts",
            )
            selected = prioritize(artifacts, 100)
            ocr_budget = 6
            page_budget = max(
                0,
                settings().max_pdf_pages
                - sum(
                    a.parsed.get("pages", 0)
                    for a in selected
                    if a.parsed and a.parsed.get("parser_fingerprint") == PARSER_FINGERPRINT
                ),
            )
            for i, a in enumerate(selected):
                if a.kind == "paper":
                    from .ingest import classify

                    if classify(a.path) == "figure":
                        a.kind = "figure"
                        db.commit()
                db.refresh(job)
                if job.state == "cancelled":
                    raise asyncio.CancelledError()
                if not a.parsed or a.parsed.get("parser_fingerprint") != PARSER_FINGERPRINT:
                    try:
                        a.parsed = await parse_bounded(
                            a,
                            await asyncio.to_thread(storage.get, a.storage_key),
                            page_budget=page_budget,
                        )
                        page_budget = max(0, page_budget - a.parsed.get("pages", 0))
                    except Exception as exc:
                        a.parsed = {
                            "text": "",
                            "anchors": [],
                            "warnings": [
                                f"Parser could not inspect this file: {type(exc).__name__}"
                            ],
                            "unavailable": True,
                        }
                    if a.parsed.get("role_hint") == "results" and a.kind == "data":
                        a.kind = "results"
                    db.commit()
                if (
                    a.kind == "paper"
                    and a.path.lower().endswith(".pdf")
                    and ocr_budget
                    and any(d.get("low_text") for d in a.parsed.get("page_details", []))
                ):
                    a.parsed, used = await recover_pages(
                        a, await asyncio.to_thread(storage.get, a.storage_key), provider, ocr_budget
                    )
                    ocr_budget -= used
                    db.commit()
                result["warnings"].extend(f"{a.path}: {w}" for w in a.parsed.get("warnings", []))
                emit(
                    db,
                    case.id,
                    "extracting",
                    f"Indexed {a.path}",
                    type="artifact",
                    artifact_id=a.id,
                    index=i + 1,
                    total=len(selected),
                )
                if (i + 1) % 10 == 0:
                    result["coverage"] = {
                        "files_discovered": len(artifacts),
                        "files_inspected": i + 1,
                    }
                    save(
                        db,
                        case,
                        job,
                        result,
                        "inspecting",
                        f"Checkpointed {i + 1} artifact inspections",
                    )
            inventory = [artifact_dict(a) for a in artifacts]
            fingerprint = hashlib.sha256(
                json.dumps(
                    {
                        "version": "completion-1",
                        "parser": PARSER_FINGERPRINT,
                        "sources": [
                            [
                                a.id,
                                a.sha256,
                                hashlib.sha256(
                                    (a.parsed or {}).get("text", "").encode()
                                ).hexdigest(),
                            ]
                            for a in artifacts
                        ],
                        "model": settings().openai_model,
                        "provider": case.provider,
                        "primary_paper": provider.primary_paper,
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            result["_source_fingerprint"] = fingerprint
            result["model"] = (
                settings().ollama_model if case.provider == "ollama" else settings().openai_model
            )
            result["coverage"] = {
                "files_discovered": len(artifacts),
                "files_inspected": sum(not a.parsed.get("unavailable") for a in selected),
                "files_unavailable": sum(bool(a.parsed.get("unavailable")) for a in selected),
                "pdf_pages_inspected": sum(a.parsed.get("pages", 0) for a in selected),
                "claims_examined": 0,
                "checks_completed": 0,
                "checks_skipped": 0,
                "unresolved_questions": 0,
            }
            if len(artifacts) > len(selected):
                result["warnings"].append(
                    "Analysis budget: 100 prioritized artifacts inspected; remaining files are inventoried only"
                )
            result["artifacts"] = [{k: v for k, v in a.items() if k != "parsed"} for a in inventory]
            claims = extract_claims(inventory)
            result["claims"] = claims
            save(
                db,
                case,
                job,
                result,
                "extracting",
                f"Extracted {len(claims)} source-anchored numerical claims",
            )
            if old_result.get("_source_fingerprint") == fingerprint and old_result.get(
                "_claims_complete"
            ):
                claims = old_result["claims"]
                provider.used = old_result.get("provider", "deterministic")
                emit(
                    db,
                    case.id,
                    "extracting",
                    "Reused validated claim-extraction checkpoint",
                    type="checkpoint",
                )
            else:
                batch = await provider.extract_claims(inventory)
                if batch:
                    claims = merge_claims(inventory, claims, batch, provider.used)
            result["_claims_complete"] = (
                provider.used != "deterministic" or case.provider == "deterministic"
            )
            result["claims"] = claims
            result["provider"] = provider.used
            result["model"] = (
                settings().ollama_model
                if provider.used == "ollama"
                else settings().openai_model
                if provider.used == "openai"
                else None
            )
            result["graph"] = graph_for(inventory, claims, [], [], [])
            save(
                db,
                case,
                job,
                result,
                "mapping",
                f"Mapping {len(claims)} claims to code, configurations, data, and saved results",
            )
            answers = {d["question_id"]: d["answer"] for d in case.decisions}
            answers.setdefault("primary-paper", provider.primary_paper)
            papers = [a for a in inventory if a["kind"] == "paper"]
            comparison_claims = [
                c
                for c in claims
                if len(papers) <= 1
                or c["artifact_id"] == answers.get("primary-paper")
                or c["artifact_id"] not in {a["id"] for a in papers}
            ]
            f7, c7, q7, handled = extended_paper_checks(
                inventory, comparison_claims, case.decisions
            )
            f1, c1 = compare_metrics(
                inventory, [c for c in comparison_claims if c["id"] not in handled], case.decisions
            )
            f2, c2 = paper_internal(claims)
            f3, c3, questions = methodology(inventory, case.decisions)
            questions.extend(execution_questions(inventory, case.decisions, provider.primary_paper))
            f4, c4 = arithmetic_checks(inventory, claims)
            f5, c5 = protocol_checks(inventory, case.decisions)
            f6, c6, q6 = expanded_checks(inventory, case.decisions)
            questions.extend(q6)
            questions.extend(q7)
            questions.extend(verification_questions(inventory, case.decisions))
            correspondence_findings = f1 + f5 + [f for f in f7 if f["kind"] == "paper_repository"]
            if correspondence_findings:
                answers = {d["question_id"]: d["answer"] for d in case.decisions}
                questions.append(
                    {
                        "id": "repository-version",
                        "title": "Does this source snapshot match the paper's experiment?",
                        "why": "A numerical difference is only directly comparable when publication version, dataset, metric definition, and result context match.",
                        "evidence": correspondence_findings[0]["evidence"],
                        "options": [
                            {
                                "value": "same",
                                "label": "Same experiment and source version",
                                "effect": "Confirm the evidence correspondence; comparable single-result discrepancies can be verified.",
                            },
                            {
                                "value": "different",
                                "label": "Different or later version",
                                "effect": "Mark the comparison inconclusive because its source correspondence differs.",
                            },
                            {
                                "value": "unknown",
                                "label": "I cannot establish that",
                                "effect": "Keep the publication-to-repository correspondence unresolved.",
                            },
                        ],
                        "answer": answers.get("repository-version"),
                    }
                )
            gate_ocr(f1 + f2 + f3 + f4 + f5 + f6 + f7, c1 + c2 + c3 + c4 + c5 + c6 + c7, questions)
            unique = {}
            for f in f1 + f2 + f3 + f4 + f5 + f6 + f7:
                if f["id"] not in unique or f["evidence_status"].startswith("verified"):
                    unique[f["id"]] = f
            findings = list(unique.values())
            previous = {f["id"]: f for f in old_result.get("findings", [])}
            retain_reviews(findings, previous)
            result.update(
                findings=findings, checks=c1 + c2 + c3 + c4 + c5 + c6 + c7, questions=questions
            )
            save(
                db,
                case,
                job,
                result,
                "checking",
                f"Completed deterministic checks; {len(findings)} findings require inspection",
            )
            same_sources = old_result.get("_source_fingerprint") == fingerprint
            answers = {d["question_id"]: d["answer"] for d in case.decisions}
            if same_sources:
                for cached in old_result.get("adaptive_questions", []):
                    if not any(q["id"] == cached["id"] for q in questions):
                        questions.append({**cached, "answer": answers.get(cached["id"])})
            history = (
                list(old_result.get("agent_actions", []))
                if same_sources and old_result.get("_revision") == case.revision
                else []
            )

            def agent_checkpoint(action):
                result.update(
                    claims=claims,
                    findings=findings,
                    checks=result["checks"],
                    questions=questions,
                    agent_actions=history,
                )
                result["adaptive_questions"] = [
                    q for q in questions if q.get("origin") == "grounded model clarification"
                ]
                save(
                    db,
                    case,
                    job,
                    result,
                    "investigating",
                    "Completed grounded action: " + action["tool"].replace("_", " "),
                )

            if not (
                same_sources
                and old_result.get("_revision") == case.revision
                and old_result.get("_agent_complete")
                and old_result.get("provider") == provider.used
            ):
                await investigate(
                    provider,
                    inventory,
                    claims,
                    findings,
                    result["checks"],
                    questions,
                    case.decisions,
                    history,
                    agent_checkpoint,
                )
            apply_interpretations(findings, questions)
            gate_ocr(findings, result["checks"], questions)
            retain_reviews(findings, previous)
            result["adaptive_questions"] = [
                q for q in questions if q.get("origin") == "grounded model clarification"
            ]
            result["_agent_complete"] = True
            result["agent_actions"] = history
            save(
                db,
                case,
                job,
                result,
                "investigating",
                "Checking available execution capabilities and experiment prerequisites",
            )
            plans, reason = execution_plan(inventory, case.decisions)
            capability = await runner_status()
            if not capability["available"] or not plans:
                result["checks"].append(
                    {
                        "id": "execution-capability",
                        "name": "Isolated re-evaluation",
                        "status": "skipped",
                        "detail": reason or capability["reason"],
                    }
                )
            else:
                if reason:
                    result["checks"].append(
                        {
                            "id": "corrected-prerequisites",
                            "name": "Corrected reconstruction prerequisites",
                            "status": "inconclusive",
                            "detail": reason,
                        }
                    )
                for spec in plans:
                    data = next(a for a in artifacts if a.id == spec["dataset_id"])
                    source_artifacts = [
                        a
                        for a in artifacts
                        if a.kind in {"code", "data", "configuration"}
                        and Path(a.path).suffix.lower()
                        in {".py", ".ipynb", ".csv", ".tsv", ".json", ".yaml", ".yml", ".toml"}
                    ]
                    source_hashes = (
                        {a.path: a.sha256 for a in source_artifacts}
                        if spec.get("execution_mode") == "original"
                        else {}
                    )
                    manifest = {
                        **spec,
                        "source_hashes": source_hashes,
                        "original_helper_sha256": hashlib.sha256(
                            Path(__file__).with_name("original_worker.py").read_bytes()
                        ).hexdigest()
                        if source_hashes
                        else None,
                        "input_sha256": data.sha256,
                        "input_decoding": "UTF-8; an optional BOM is removed. The worker separately hashes the exact decoded UTF-8 text.",
                        "worker_sha256": hashlib.sha256(
                            Path(__file__)
                            .with_name("sandbox_worker.py")
                            .read_text(encoding="utf-8")
                            .encode()
                        ).hexdigest(),
                        "environment_image": "OpenAI disposable 1g Python sandbox; package versions recorded by the actual run"
                        if capability["provider"] == "openai"
                        else settings().e2b_template
                        if capability["provider"] == "e2b"
                        else settings().docker_image,
                        "revision": case.revision,
                        "classification": "original_execution"
                        if spec.get("execution_mode") == "original"
                        else "reconstruction"
                        if spec["variant"] == "baseline"
                        else "corrected_protocol",
                        "runner": capability["provider"],
                    }
                    fingerprint = hashlib.sha256(
                        json.dumps(
                            {
                                k: v
                                for k, v in manifest.items()
                                if k not in {"revision", "preprocessing_policy"}
                            },
                            sort_keys=True,
                        ).encode()
                    ).hexdigest()
                    run = db.scalar(
                        select(Execution).where(
                            Execution.case_id == case.id,
                            Execution.fingerprint == fingerprint,
                            Execution.status == "completed",
                        )
                    )
                    if not run:
                        run = Execution(
                            case_id=case.id,
                            fingerprint=fingerprint,
                            manifest=manifest,
                            status="running",
                        )
                        db.add(run)
                        db.commit()

                        def started(ref):
                            run.sandbox_id = ref
                            db.commit()

                        emit(
                            db,
                            case.id,
                            "investigating",
                            f"Running {spec['variant']} in {capability['provider']}",
                            type="execution",
                            execution_id=run.id,
                        )
                        try:
                            executable_spec = dict(spec)
                            if spec.get("execution_mode") == "original":
                                if (
                                    len(source_artifacts) > 200
                                    or sum(a.size for a in source_artifacts) > 50 * 1024**2
                                ):
                                    raise ValueError(
                                        "Original source bundle exceeds 200 files / 50 MB; inspect its required inputs"
                                    )
                                executable_spec["source_files"] = [
                                    {
                                        "path": a.path,
                                        "data": base64.b64encode(
                                            await asyncio.to_thread(storage.get, a.storage_key)
                                        ).decode(),
                                    }
                                    for a in source_artifacts
                                ]
                            run.output = await run_isolated(
                                case.id,
                                run.id,
                                storage.get(data.storage_key).decode("utf-8-sig"),
                                executable_spec,
                                started,
                            )
                            if source_hashes and any(
                                run.output.get("source_hashes", {}).get(path) != hash
                                for path, hash in source_hashes.items()
                            ):
                                raise ValueError(
                                    "Original source hashes did not match the immutable case snapshot"
                                )
                            if (
                                source_hashes
                                and run.output.get("helper_sha256")
                                != manifest["original_helper_sha256"]
                            ):
                                raise ValueError("Original harness hash differed from this release")
                            run.status = "completed"
                        except asyncio.CancelledError:
                            run.status = "cancelled"
                            db.commit()
                            raise
                        except Exception as exc:
                            run.status = "failed"
                            run.output = {"error": (str(exc) or type(exc).__name__)[:1500]}
                        db.commit()
                    result["executions"].append(execution_dict(run))
                    result["checks"].append(
                        {
                            "id": "execution-" + run.id,
                            "name": "Supported CPU evaluation",
                            "status": "passed" if run.status == "completed" else "inconclusive",
                            "detail": f"{spec['variant']}: {run.status}. "
                            + (
                                (
                                    "Original source executed in isolation; inspect measured provenance and publication comparability."
                                    if spec.get("execution_mode") == "original"
                                    else "Trusted reconstruction; not an independent reproduction."
                                )
                                if run.status == "completed"
                                else run.output.get(
                                    "error", "No successful measurement was returned."
                                )
                            ),
                        }
                    )
                    save(
                        db,
                        case,
                        job,
                        result,
                        "investigating",
                        f"{spec['variant'].replace('_', ' ').title()}: {run.status}",
                    )
            run_findings, run_checklist = execution_checks(result["executions"], case.decisions)
            reproduced_findings, reproduced_checks, reproduced_questions = paper_execution_checks(
                comparison_claims, result["executions"], case.decisions
            )
            run_findings.extend(reproduced_findings)
            run_checklist.extend(reproduced_checks)
            questions.extend(reproduced_questions)
            gate_ocr(run_findings, run_checklist, questions)
            retain_reviews(run_findings, previous)
            findings.extend(run_findings)
            result["findings"] = findings
            result["checks"].extend(run_checklist)
            result["warnings"].extend(provider.warnings)
            result["provider"] = provider.used
            result["model"] = (
                settings().ollama_model
                if provider.used == "ollama"
                else settings().openai_model
                if provider.used == "openai"
                else None
            )
            if provider.used == "deterministic":
                result["warnings"].append(
                    "Language-model analysis unavailable or disabled. Findings below come from deterministic extraction and checks; contextual claim coverage is limited."
                )
            result["coverage"].update(
                claims_examined=len(claims),
                checks_completed=sum(
                    c["status"] in {"passed", "flagged"} for c in result["checks"]
                ),
                checks_skipped=sum(
                    c["status"] in {"skipped", "inconclusive"} for c in result["checks"]
                ),
                unresolved_questions=sum(
                    not q.get("answer") or q.get("answer") == "unknown" for q in questions
                ),
            )
            result["graph"] = graph_for(
                inventory, claims, findings, result["executions"], questions, result["checks"]
            )
            pending = result["coverage"]["unresolved_questions"]
            terminal = (
                "awaiting_input"
                if pending
                else "partially_complete"
                if result["coverage"]["checks_skipped"] or result["warnings"]
                else "review_ready"
            )
            save(
                db,
                case,
                job,
                result,
                terminal,
                "Evidence ready. Human interpretation remains part of this investigation.",
            )
            job.state = "completed"
            db.commit()
        except asyncio.CancelledError:
            await terminate(case.id)
            db.refresh(case)
            db.refresh(job)
            shutting_down = STOP_EVENT is not None and STOP_EVENT.is_set()
            case.status = "interrupted" if shutting_down else "cancelled"
            job.state = "interrupted" if shutting_down else "cancelled"
            db.commit()
            emit(
                db,
                case.id,
                case.status,
                "Worker stopping; checkpoints retained for automatic continuation"
                if shutting_down
                else "Investigation cancelled; completed evidence has been retained",
            )
            raise
        except Exception as exc:
            db.rollback()
            case = db.get(Case, job.case_id)
            job = db.get(Job, job_id)
            if case and job:
                case.status = "failed"
                job.state = "failed"
                job.error = str(exc)[:1500]
                db.commit()
                emit(
                    db, case.id, "failed", f"Investigation stopped: {str(exc)[:500]}", type="error"
                )


async def worker(stop):
    global STOP_EVENT
    STOP_EVENT = stop
    from .recovery import reconcile

    await reconcile()
    last_sweep = 0
    while not stop.is_set():
        if asyncio.get_running_loop().time() - last_sweep > 3600:
            await expire_cases()
            last_sweep = asyncio.get_running_loop().time()
        with Session() as db:
            job = db.scalar(select(Job).where(Job.state == "queued").order_by(Job.created_at))
            if job:
                job.state = "running"
                job.started_at = utcnow()
                db.commit()
                job_id = job.id
                case_id = job.case_id
            else:
                job_id = None
        if job_id:
            with Session() as budget_db:
                elapsed = budget_db.get(Case, case_id).result.get("_elapsed_seconds", 0)
            TIMINGS[job_id] = (time.monotonic(), elapsed)
            task = asyncio.create_task(analyze(job_id))
            RUNNING[case_id] = task
            try:
                await asyncio.wait_for(task, max(1, settings().max_case_seconds - elapsed))
            except asyncio.CancelledError:
                if stop.is_set():
                    raise
            except TimeoutError:
                with Session() as db:
                    job = db.get(Job, job_id)
                    if job:
                        await terminate(job.case_id)
                        job.state = "failed"
                        job.error = "Case exceeded the ten-minute execution budget"
                        case = db.get(Case, job.case_id)
                        if case:
                            case.status = "partially_complete"
                        db.commit()
                        emit(db, job.case_id, "partially_complete", job.error, type="error")
            finally:
                RUNNING.pop(case_id, None)
                TIMINGS.pop(job_id, None)
                PROVIDERS.pop(job_id, None)
        else:
            try:
                await asyncio.wait_for(stop.wait(), 0.4)
            except TimeoutError:
                pass
