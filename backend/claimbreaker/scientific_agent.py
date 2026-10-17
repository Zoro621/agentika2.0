"""Bounded adaptive investigation: grounded tools, real checks, consequential questions."""

from .checks import compare_metrics, methodology, paper_internal, stable, locate
from .paper_checks import extended_paper_checks
from .research_checks import expanded_checks
from .additional_checks import arithmetic_checks
from .protocol_checks import protocol_checks
from .claim_validation import merge_claims


def upsert(target, records):
    positions = {r["id"]: i for i, r in enumerate(target)}
    for record in records:
        if record["id"] in positions:
            target[positions[record["id"]]] = record
        else:
            positions[record["id"]] = len(target)
            target.append(record)


def grounded_question(proposal, inventory, findings, decisions):
    q = proposal.question
    if q is None:
        return None
    artifact = next((a for a in inventory if a["id"] == q.artifact_id), None)
    if not artifact:
        return None
    normalized = " ".join(q.quote.split())
    if len(normalized) < 10:
        return None
    texts = [artifact["parsed"].get("text", "")] + [
        a["text"] for a in artifact["parsed"].get("anchors", [])
    ]
    if not any(normalized in " ".join(text.split()) for text in texts):
        return None
    evidence = [locate(artifact, q.quote)]
    answers = {d["question_id"]: d["answer"] for d in decisions}
    related = [id for id in q.finding_ids if any(f["id"] == id for f in findings)]
    if q.purpose == "feature_availability":
        if not any(
            q.subject in [c["name"] for c in a["parsed"].get("profile", {}).get("columns", [])]
            for a in inventory
        ):
            return None
        id = "availability:" + q.subject
        if len(id) > 100:
            return None
        options = [
            ("before", "Available before prediction", "Keep the feature in the evaluation."),
            (
                "after",
                "Available only afterward",
                "Exclude this feature from a separately labeled corrected evaluation.",
            ),
            ("unknown", "Uncertain", "Keep availability unresolved."),
        ]
    elif q.purpose == "experiment_correspondence":
        id = "repository-version"
        options = [
            (
                "same",
                "Same experiment and source version",
                "Permit comparable deterministic artifact checks to establish a discrepancy.",
            ),
            (
                "different",
                "Different source correspondence",
                "Keep affected comparisons inconclusive.",
            ),
            ("unknown", "I cannot establish that", "Retain the correspondence question."),
        ]
    else:
        if not related:
            return None
        id = stable("interpretation", q.artifact_id + q.quote + q.title)
        options = [
            (
                "confirmed",
                "The stated interpretation applies",
                "Retain the concern with this researcher-established context; this does not by itself verify a result.",
            ),
            (
                "alternative",
                "A different interpretation applies",
                "Mark related findings inconclusive and require revised scientific context.",
            ),
            (
                "unknown",
                "I cannot establish that",
                "Mark dependent interpretation inconclusive; independent checks continue.",
            ),
        ]
    return {
        "id": id,
        "title": q.title,
        "why": q.why,
        "evidence": evidence,
        "options": [{"value": v, "label": label, "effect": effect} for v, label, effect in options],
        "answer": answers.get(id),
        "origin": "grounded model clarification",
        "related_findings": related,
        "purpose": q.purpose,
    }


def apply_interpretations(findings, questions):
    for question in questions:
        if question.get("purpose") != "interpretation" or not question.get("answer"):
            continue
        for finding in findings:
            if finding["id"] not in question.get("related_findings", []):
                continue
            finding["human_context"] = {"question": question["title"], "answer": question["answer"]}
            if question["answer"] in {"alternative", "unknown"}:
                finding["evidence_status"] = "inconclusive"
                finding["limitations"] = [
                    *finding.get("limitations", []),
                    "The researcher did not establish this interpretation; dependent conclusions remain inconclusive",
                ]


async def investigate(
    provider, inventory, claims, findings, checks, questions, decisions, history, checkpoint
):
    for _ in range(max(0, 8 - len(history))):
        provider.questions = questions
        proposal = await provider.next_action(inventory, claims, findings, history)
        if not proposal or proposal.tool == "finish":
            break
        action = proposal.model_dump()
        signature = {k: v for k, v in action.items() if k != "summary"}
        if any(h.get("signature") == signature for h in history):
            break
        action["signature"] = signature
        artifact = next((a for a in inventory if a["id"] == proposal.artifact_id), None)
        tool = proposal.tool
        if tool == "inspect_artifact":
            if not artifact:
                continue
            parsed = artifact["parsed"]
            profile = parsed.get("profile", {})
            action["result"] = {
                "path": artifact["path"],
                "text": parsed.get("text", "")[:5000],
                "code": parsed.get("code"),
                "profile": {
                    k: v
                    for k, v in profile.items()
                    if k
                    in {"rows", "sampled", "repeated_entities", "duplicate_rows", "time_columns"}
                },
                "columns": [
                    {k: v for k, v in c.items() if k != "examples"}
                    for c in profile.get("columns", [])[:100]
                ],
            }
        elif tool == "search_evidence":
            words = set(proposal.query.lower().split())
            if not words:
                continue
            hits = [
                (sum(w in anchor["text"].lower() for w in words), anchor)
                for a in inventory
                for anchor in a["parsed"].get("anchors", [])
            ]
            hits.sort(key=lambda hit: hit[0], reverse=True)
            action["result"] = {"anchors": [a for score, a in hits[:6] if score]}
        elif tool == "ask_question":
            question = grounded_question(proposal, inventory, findings, decisions)
            if not question:
                continue
            if not any(q["id"] == question["id"] for q in questions):
                questions.append(question)
            action["result"] = {
                "question_id": question["id"],
                "effect": "A versioned answer changes dependent interpretation or the corrected execution plan.",
            }
        elif tool == "extract_claims":
            if not artifact or artifact["kind"] not in {"paper", "documentation"}:
                continue
            batch = await provider.extract_claims([artifact])
            before = len(claims)
            if batch:
                claims[:] = merge_claims(inventory, claims, batch, provider.used)
            action["result"] = {"additional_grounded_claims": len(claims) - before}
        elif tool in {"run_check", "compare_metrics", "inspect_method"}:
            name = proposal.check or (
                "metrics"
                if tool == "compare_metrics"
                else "methodology"
                if tool == "inspect_method"
                else None
            )
            new_findings, new_checks, new_questions = [], [], []
            if name == "metrics":
                papers = [a for a in inventory if a["kind"] == "paper"]
                answers = {d["question_id"]: d["answer"] for d in decisions}
                answers.setdefault("primary-paper", getattr(provider, "primary_paper", None))
                eligible = [
                    c
                    for c in claims
                    if len(papers) <= 1
                    or c["artifact_id"] == answers.get("primary-paper")
                    or c["artifact_id"] not in {a["id"] for a in papers}
                ]
                f, c, q, handled = extended_paper_checks(inventory, eligible, decisions)
                f2, c2 = compare_metrics(
                    inventory, [c for c in eligible if c["id"] not in handled], decisions
                )
                new_findings = f + f2
                new_checks = c + c2
                new_questions = q
            elif name == "methodology":
                new_findings, new_checks, new_questions = methodology(inventory, decisions)
            elif name == "partitions":
                new_findings, new_checks, new_questions = expanded_checks(inventory, decisions)
            elif name == "protocol":
                new_findings, new_checks = protocol_checks(inventory, decisions)
            elif name == "arithmetic":
                new_findings, new_checks = arithmetic_checks(inventory, claims)
            elif name == "paper":
                new_findings, new_checks = paper_internal(claims)
            else:
                continue
            upsert(findings, new_findings)
            upsert(checks, new_checks)
            for q in new_questions:
                if not any(existing["id"] == q["id"] for existing in questions):
                    questions.append(q)
            action["result"] = {
                "check_family": name,
                "checks": new_checks[:12],
                "finding_ids": [f["id"] for f in new_findings],
                "questions": [q["id"] for q in new_questions],
            }
        else:
            continue
        history.append(action)
        apply_interpretations(findings, questions)
        checkpoint(action)
    return history
