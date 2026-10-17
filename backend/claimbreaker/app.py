import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse, quote
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.gzip import GZipMiddleware
from sqlalchemy import select, func, delete
from .config import settings
from .db import Session, Case, Artifact, Job, Event, Execution, initialize, emit, utcnow, utc_iso
from .schemas import CaseCreate, GithubSource, DecisionInput, ReviewInput
from .ingest import unpack, import_files, fetch_github, IntakeError
from .engine import worker, artifact_dict, execution_dict, cancel_analysis, RUNNING
from .providers import ollama_status
from .execution import runner_status, terminate
from .reports import pdf_report, json_report, evidence_bundle
from .samples import SAMPLES, build_sample
from .http_limits import BodyLimitMiddleware
from .parser_process import parse_bounded
from . import storage


@asynccontextmanager
async def lifespan(app):
    initialize()
    stop = asyncio.Event()
    task = asyncio.create_task(worker(stop))
    yield
    stop.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="ClaimBreaker API", version="0.1.0", lifespan=lifespan)
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings().session_secret,
    same_site="strict",
    https_only=settings().secure_cookies,
    max_age=7 * 86400,
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if not request.url.path.startswith(("/api/", "/docs", "/redoc", "/openapi")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        )
    if settings().secure_cookies:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    elif request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(IntakeError)
async def intake_error(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


def owner(request):
    if not request.session.get("owner"):
        request.session["owner"] = secrets.token_hex(24)
    return request.session["owner"]


def owned(db, request, case_id):
    case = db.get(Case, case_id)
    if not case or case.owner != owner(request):
        raise HTTPException(404, "Case not found in this private session")
    return case


def case_payload(db, case):
    artifacts = list(
        db.scalars(select(Artifact).where(Artifact.case_id == case.id).order_by(Artifact.path))
    )
    jobs = list(
        db.scalars(
            select(Job).where(Job.case_id == case.id).order_by(Job.created_at.desc()).limit(5)
        )
    )
    return {
        "id": case.id,
        "title": case.title,
        "status": case.status,
        "revision": case.revision,
        "provider": case.provider,
        "created_at": utc_iso(case.created_at),
        "updated_at": utc_iso(case.updated_at),
        "sources": case.sources,
        "decisions": case.decisions,
        "result": case.result,
        "artifacts": [
            {
                "id": a.id,
                "path": a.path,
                "kind": a.kind,
                "size": a.size,
                "sha256": a.sha256,
                "warnings": a.parsed.get("warnings", []) if a.parsed else [],
            }
            for a in artifacts
        ],
        "jobs": [
            {"id": j.id, "state": j.state, "checkpoint": j.checkpoint, "error": j.error}
            for j in jobs
        ],
    }


def enqueue(db, case):
    if case.status == "deleting":
        raise HTTPException(409, "Case deletion is in progress")
    current = db.scalar(
        select(Job).where(Job.case_id == case.id, Job.state.in_(["queued", "running"]))
    )
    if current:
        return current
    if not db.scalar(select(func.count()).select_from(Artifact).where(Artifact.case_id == case.id)):
        raise HTTPException(400, "Add at least one source first")
    case.status = "queued"
    case.updated_at = utcnow()
    job = Job(case_id=case.id, revision=case.revision)
    db.add(job)
    db.commit()
    emit(db, case.id, "queued", "Investigation queued", type="status")
    return job


@app.get("/api/v1/health/live")
def live():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/v1/cases/{case_id}/artifacts/{artifact_id}/pages/{page}")
async def pdf_page(case_id: str, artifact_id: str, page: int, request: Request, quote: str = ""):
    if len(quote) > 1800 or not 1 <= page <= 100:
        raise HTTPException(400, "Page or highlight exceeds support limits")
    with Session() as db:
        owned(db, request, case_id)
        artifact = db.get(Artifact, artifact_id)
        if (
            not artifact
            or artifact.case_id != case_id
            or not artifact.path.lower().endswith(".pdf")
        ):
            raise HTTPException(404, "PDF source not found")
        result = await parse_bounded(
            artifact,
            await asyncio.to_thread(storage.get, artifact.storage_key),
            operation="render",
            page=page,
            quote=quote,
        )
        if result.get("unavailable"):
            raise HTTPException(422, "Page could not be rendered within the parser budget")
        return result


@app.get("/api/v1/health/ready")
def ready():
    with Session() as db:
        db.execute(select(1))
    return {
        "status": "ready",
        "persistence": "postgresql"
        if not settings().database_url.startswith("sqlite")
        else "sqlite",
        "offline": settings().offline,
    }


@app.get("/api/v1/capabilities")
async def capabilities():
    import os

    ollama, runner = await asyncio.gather(ollama_status(), runner_status())
    return {
        "offline": settings().offline,
        "openai": {
            "configured": bool(os.getenv("OPENAI_API_KEY")) and not settings().offline,
            "model": settings().openai_model,
        },
        "ollama": ollama,
        "runner": runner,
        "limits": {
            "upload_mb": 50,
            "extracted_mb": 250,
            "entries": 2000,
            "inspected_artifacts": 100,
            "pdf_pages": 100,
            "case_seconds": settings().max_case_seconds,
        },
        "supported": [
            "PDF/text claims",
            "Python/Notebook AST",
            "CSV profiling",
            "Saved metric comparisons",
            "Human-led interpretation",
            "Isolated supported Python/notebook execution",
            "Cross-validation and corrected grouped/temporal CPU evaluation",
            "Rendered PDF citations and bounded scanned-page recovery",
        ],
        "unsupported": [
            "Arbitrary repository execution",
            "GPU training",
            "Universal scientific validity assessment",
        ],
        "storage": "private hosted storage" if settings().supabase_url else "local private storage",
    }


@app.get("/api/v1/samples")
def samples():
    return SAMPLES


@app.get("/api/v1/samples/{kind}/download")
async def sample_download(kind: str):
    if kind not in {s["id"] for s in SAMPLES}:
        raise HTTPException(404, "Sample not found")
    data = await asyncio.to_thread(build_sample, kind)
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="claimbreaker-{kind}.zip"'},
    )


@app.post("/api/v1/cases", status_code=201)
def create_case(payload: CaseCreate, request: Request):
    with Session() as db:
        who = owner(request)
        count = db.scalar(
            select(func.count())
            .select_from(Case)
            .where(Case.owner == who, Case.created_at > utcnow() - timedelta(days=1))
        )
        if count >= settings().max_session_cases:
            raise HTTPException(429, "Daily investigation limit reached for this session")
        case = Case(
            owner=who,
            title=payload.title,
            provider=settings().provider if payload.provider == "auto" else payload.provider,
        )
        db.add(case)
        db.commit()
        return case_payload(db, case)


@app.get("/api/v1/cases")
def list_cases(request: Request):
    with Session() as db:
        cases = db.scalars(
            select(Case)
            .where(Case.owner == owner(request))
            .order_by(Case.updated_at.desc())
            .limit(30)
        )
        return [
            {
                "id": c.id,
                "title": c.title,
                "status": c.status,
                "created_at": utc_iso(c.created_at),
                "findings": len(c.result.get("findings", [])),
            }
            for c in cases
        ]


@app.get("/api/v1/cases/{case_id}")
def get_case(case_id: str, request: Request):
    with Session() as db:
        return case_payload(db, owned(db, request, case_id))


@app.post("/api/v1/cases/{case_id}/artifacts")
async def upload(case_id: str, request: Request, file: UploadFile = File(...)):
    with Session() as db:
        case = owned(db, request, case_id)
        if case.status not in {"received", "failed"}:
            raise HTTPException(
                409, "Source snapshots are immutable after analysis starts; create a new case"
            )
        content = await file.read(settings().max_upload + 1)
        files, ignored = await asyncio.to_thread(unpack, file.filename or "upload.zip", content)
        created = await asyncio.to_thread(import_files, db, case.id, files)
        case.sources = case.sources + [
            {
                "type": "upload",
                "name": file.filename,
                "accepted": len(created),
                "ignored": len(ignored),
                "acquired_at": utcnow().isoformat(),
            }
        ]
        if case.title == "Untitled investigation":
            case.title = (file.filename or "Research project").rsplit(".", 1)[0].replace("_", " ")
        db.commit()
        emit(
            db,
            case.id,
            "received",
            f"Accepted {len(created)} artifacts; ignored {len(ignored)} unsupported/private paths",
            type="intake",
        )
        return {
            "artifacts": [
                {"id": a.id, "path": a.path, "kind": a.kind, "size": a.size} for a in created
            ],
            "ignored": ignored[:100],
        }


@app.post("/api/v1/cases/{case_id}/sources/github")
async def github(case_id: str, payload: GithubSource, request: Request):
    with Session() as db:
        case = owned(db, request, case_id)
        if case.status != "received":
            raise HTTPException(409, "Create a new case to analyze another source snapshot")
        has_paper = bool(
            db.scalar(
                select(Artifact.id)
                .where(Artifact.case_id == case.id, Artifact.kind == "paper")
                .limit(1)
            )
        )
        try:
            files, ignored, source = await fetch_github(
                payload.url, payload.ref, discover_papers=not has_paper
            )
        except IntakeError:
            raise
        except Exception:
            raise HTTPException(502, "GitHub acquisition failed. Retry or upload a source ZIP")
        created = await asyncio.to_thread(import_files, db, case.id, files)
        case.sources = case.sources + [{**source, "acquired_at": utcnow().isoformat()}]
        if case.title == "Untitled investigation":
            case.title = source["url"].rsplit("/", 1)[1]
        db.commit()
        emit(
            db,
            case.id,
            "received",
            f"Pinned repository snapshot {source['commit'][:12]}",
            type="intake",
        )
        return {"source": source, "artifacts": len(created), "ignored": len(ignored)}


@app.post("/api/v1/cases/{case_id}/sample/{kind}")
async def add_sample(case_id: str, kind: str, request: Request):
    with Session() as db:
        case = owned(db, request, case_id)
        if case.status != "received":
            raise HTTPException(409, "Case already started")
        if kind not in {s["id"] for s in SAMPLES}:
            raise HTTPException(404, "Sample not found")
        content = await asyncio.to_thread(build_sample, kind)
        files, _ = unpack("sample.zip", content)
        await asyncio.to_thread(import_files, db, case.id, files)
        case.title = next(s["title"] for s in SAMPLES if s["id"] == kind)
        case.sources = case.sources + [
            {
                "type": "synthetic_sample",
                "id": kind,
                "label": "Synthetic demo; not published research",
                "acquired_at": utcnow().isoformat(),
            }
        ]
        db.commit()
        enqueue(db, case)
        return case_payload(db, case)


@app.post("/api/v1/cases/{case_id}/start")
def start(case_id: str, request: Request):
    with Session() as db:
        case = owned(db, request, case_id)
        job = enqueue(db, case)
        return {"job_id": job.id, "state": job.state}


@app.post("/api/v1/cases/{case_id}/rerun")
def rerun(case_id: str, request: Request):
    with Session() as db:
        case = owned(db, request, case_id)
        if db.scalar(
            select(Job).where(Job.case_id == case.id, Job.state.in_(["running", "queued"]))
        ):
            raise HTTPException(409, "Investigation already running")
        case.revision += 1
        db.commit()
        job = enqueue(db, case)
        return {"job_id": job.id}


@app.post("/api/v1/cases/{case_id}/decisions")
def decision(case_id: str, payload: DecisionInput, request: Request):
    with Session() as db:
        case = owned(db, request, case_id)
        if db.scalar(
            select(Job).where(Job.case_id == case.id, Job.state.in_(["running", "queued"]))
        ):
            raise HTTPException(
                409, "Wait for the current investigation to finish before changing its assumptions"
            )
        question = next(
            (q for q in case.result.get("questions", []) if q["id"] == payload.question_id), None
        )
        if not question or payload.answer not in {o["value"] for o in question["options"]}:
            raise HTTPException(400, "Answer is not a valid option for this question")
        case.revision += 1
        case.decisions = case.decisions + [
            {**payload.model_dump(), "revision": case.revision, "at": utcnow().isoformat()}
        ]
        db.commit()
        emit(
            db,
            case.id,
            "checking",
            "Human judgment updated: " + question["title"],
            type="decision",
            question_id=question["id"],
            answer=payload.answer,
        )
        job = enqueue(db, case)
        return {"revision": case.revision, "job_id": job.id}


@app.post("/api/v1/cases/{case_id}/findings/{finding_id}/review")
def review(case_id: str, finding_id: str, payload: ReviewInput, request: Request):
    with Session() as db:
        case = owned(db, request, case_id)
        if case.status in {
            "queued",
            "inspecting",
            "extracting",
            "mapping",
            "checking",
            "investigating",
        }:
            raise HTTPException(409, "Wait for the investigation to settle before reviewing")
        data = json.loads(json.dumps(case.result))
        item = next((f for f in data.get("findings", []) if f["id"] == finding_id), None)
        if not item:
            raise HTTPException(404, "Finding not found")
        item.update(
            review_status=payload.status, review_note=payload.note, reviewed_at=utcnow().isoformat()
        )
        case.result = data
        db.commit()
        emit(
            db,
            case.id,
            case.status,
            f"Finding {payload.status}: {item['title']}",
            type="review",
            finding_id=finding_id,
        )
        return item


@app.post("/api/v1/cases/{case_id}/cancel")
async def cancel(case_id: str, request: Request):
    with Session() as db:
        case = owned(db, request, case_id)
        for j in db.scalars(
            select(Job).where(Job.case_id == case.id, Job.state.in_(["queued", "running"]))
        ):
            j.state = "cancelled"
        case.status = "cancelled"
        db.commit()
        await cancel_analysis(case.id)
        emit(db, case.id, "cancelled", "Cancellation requested", type="status")
        return {"status": "cancelled"}


@app.get("/api/v1/cases/{case_id}/events")
async def events(case_id: str, request: Request, after: int = 0):
    with Session() as db:
        owned(db, request, case_id)
    try:
        cursor = max(after, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        cursor = after

    async def stream():
        nonlocal cursor
        for _ in range(3600):
            if await request.is_disconnected():
                break
            with Session() as db:
                # Recheck deletion/ownership while the stream is open.
                case = db.get(Case, case_id)
                if not case or case.owner != request.session.get("owner"):
                    break
                rows = list(
                    db.scalars(
                        select(Event)
                        .where(Event.case_id == case_id, Event.id > cursor)
                        .order_by(Event.id)
                        .limit(100)
                    )
                )
                for e in rows:
                    cursor = e.id
                    body = {
                        "id": e.id,
                        "stage": e.stage,
                        "type": e.type,
                        "message": e.message,
                        "payload": e.payload,
                        "created_at": utc_iso(e.created_at),
                    }
                    yield f"id: {e.id}\ndata: {json.dumps(body)}\n\n"
            if not rows:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.7)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.get("/api/v1/cases/{case_id}/graph")
def graph(case_id: str, request: Request):
    with Session() as db:
        return owned(db, request, case_id).result.get("graph", {"nodes": [], "edges": []})


@app.get("/api/v1/cases/{case_id}/findings")
def findings(case_id: str, request: Request):
    with Session() as db:
        return owned(db, request, case_id).result.get("findings", [])


@app.get("/api/v1/cases/{case_id}/artifacts/{artifact_id}")
def artifact(case_id: str, artifact_id: str, request: Request, raw: bool = False):
    from . import storage

    with Session() as db:
        owned(db, request, case_id)
        item = db.get(Artifact, artifact_id)
        if not item or item.case_id != case_id:
            raise HTTPException(404, "Artifact not found")
        if raw:
            media = (
                "application/pdf"
                if item.path.lower().endswith(".pdf")
                else "application/octet-stream"
            )
            return Response(
                storage.get(item.storage_key),
                media_type=media,
                headers={
                    "Content-Disposition": f"inline; filename*=UTF-8''{quote(Path(item.path).name)}"
                },
            )
        public = artifact_dict(item)
        parsed = dict(public["parsed"])
        if "profile" in parsed:
            parsed["profile"] = {
                k: v
                for k, v in parsed["profile"].items()
                if k not in {"row_hashes", "partition_hashes"}
            }
        public["parsed"] = parsed
        return public


@app.get("/api/v1/cases/{case_id}/exports/{format}")
async def export(case_id: str, format: str, request: Request):
    with Session() as db:
        case = owned(db, request, case_id)
        if format == "json":
            data, media, ext = json_report(case), "application/json", "json"
        elif format == "pdf":
            data, media, ext = await asyncio.to_thread(pdf_report, case), "application/pdf", "pdf"
        elif format == "zip":
            artifacts = list(db.scalars(select(Artifact).where(Artifact.case_id == case.id)))
            data, media, ext = (
                await asyncio.to_thread(evidence_bundle, case, artifacts),
                "application/zip",
                "zip",
            )
        else:
            raise HTTPException(404, "Choose pdf, json, or zip")
        return Response(
            data,
            media_type=media,
            headers={
                "Content-Disposition": f'attachment; filename="claimbreaker-{case.id[:8]}.{ext}"'
            },
        )


@app.delete("/api/v1/cases/{case_id}")
async def remove(case_id: str, request: Request):
    from . import storage

    with Session() as db:
        case = owned(db, request, case_id)
        if case_id in RUNNING or db.scalar(
            select(Job).where(Job.case_id == case.id, Job.state == "running")
        ):
            raise HTTPException(
                409, "Cancel the investigation and wait for it to stop before deleting"
            )
        for job in db.scalars(select(Job).where(Job.case_id == case.id, Job.state == "queued")):
            job.state = "cancelled"
        case.status = "deleting"
        db.commit()
        await terminate(case.id)
        artifacts = list(db.scalars(select(Artifact).where(Artifact.case_id == case.id)))
        for a in artifacts:
            await asyncio.to_thread(storage.delete, a.storage_key)
        db.delete(case)
        db.commit()
        return {"deleted": True}


dist = Path(__file__).resolve().parents[2] / "dist"
if dist.exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Endpoint not found")
        return FileResponse(dist / "index.html")
