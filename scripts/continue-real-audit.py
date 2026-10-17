"""Continue the test's own persisted case with evidence-established operator choices."""

import asyncio, json
from pathlib import Path
from claimbreaker.db import Session, Case, Job, utcnow, emit
from claimbreaker.app import enqueue, case_payload
from claimbreaker.reports import pdf_report, json_report, evidence_bundle
from claimbreaker.db import Artifact
from sqlalchemy import select


async def main():
    root = Path("tmp/real-paper-audit")
    id = json.loads((root / "provenance.json").read_text())["case_id"]
    with Session() as db:
        case = db.get(Case, id)
        paper = next(
            a
            for a in db.scalars(select(Artifact).where(Artifact.case_id == id))
            if a.path == "joss.00638.pdf"
        )
        decisions = [
            (
                "primary-paper",
                paper.id,
                "Validation operator selected the actual supplied JOSS publication, rather than a repository example/figure PDF.",
            ),
            (
                "experiment-dataset",
                "unknown",
                "This software publication does not define one corresponding empirical benchmark; no dataset correspondence is invented.",
            ),
        ]
        for qid, answer, rationale in decisions:
            if any(q["id"] == qid for q in case.result.get("questions", [])):
                case.revision += 1
                case.decisions = [
                    *case.decisions,
                    dict(
                        question_id=qid,
                        answer=answer,
                        rationale=rationale,
                        revision=case.revision,
                        at=utcnow().isoformat(),
                    ),
                ]
        db.commit()
        emit(
            db,
            id,
            "checking",
            "Validation operator established primary publication; empirical dataset remains unresolved",
            type="decision",
        )
        enqueue(db, case)
    for _ in range(150):
        await asyncio.sleep(3)
        with Session() as db:
            case = db.get(Case, id)
            if case.status in {"review_ready", "partially_complete", "awaiting_input", "failed"}:
                payload = case_payload(db, case)
                (root / "case.json").write_text(json.dumps(payload, indent=2))
                (root / "claimbreaker-real-paper.pdf").write_bytes(pdf_report(case))
                (root / "claimbreaker-real-paper.json").write_bytes(json_report(case))
                (root / "claimbreaker-real-paper.zip").write_bytes(
                    evidence_bundle(
                        case, list(db.scalars(select(Artifact).where(Artifact.case_id == id)))
                    )
                )
                summary = {
                    "status": case.status,
                    "provider": case.result.get("provider"),
                    "model": case.result.get("model"),
                    "coverage": case.result.get("coverage"),
                    "claims": len(case.result.get("claims", [])),
                    "findings": [
                        {"title": f["title"], "status": f["evidence_status"]}
                        for f in case.result.get("findings", [])
                    ],
                    "executions": len(case.result.get("executions", [])),
                    "questions": [
                        {"title": q["title"], "answer": q.get("answer")}
                        for q in case.result.get("questions", [])
                    ],
                    "warnings": case.result.get("warnings", []),
                    "note": "Full supported audit of actual published JOSS software paper and pinned repository. No directly corresponding single empirical experiment was established; numerical reproduction remains inconclusive.",
                }
                (root / "summary.json").write_text(json.dumps(summary, indent=2))
                print(json.dumps(summary, ensure_ascii=True), flush=True)
                return
    raise TimeoutError("Continuation did not settle")


asyncio.run(main())
