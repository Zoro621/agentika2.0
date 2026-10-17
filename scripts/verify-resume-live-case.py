"""Verify the completed live case resumes after the execution-question graph repair."""

import asyncio, json
from pathlib import Path
from claimbreaker.db import Session, Case, Artifact
from claimbreaker.app import enqueue, case_payload
from claimbreaker.reports import pdf_report, json_report, evidence_bundle
from sqlalchemy import select


async def main():
    root = Path("tmp/human-loop-acceptance")
    old = json.loads((root / "after.json").read_text())
    id = old["id"]
    expected = {r["id"] for r in old["result"]["executions"]}
    with Session() as db:
        case = db.get(Case, id)
        enqueue(db, case)
    for _ in range(150):
        await asyncio.sleep(3)
        with Session() as db:
            case = db.get(Case, id)
            if case.status in {"review_ready", "partially_complete", "awaiting_input", "failed"}:
                assert case.status != "failed", [
                    (j.state, j.error)
                    for j in db.scalars(
                        select(__import__("claimbreaker.db", fromlist=["Job"]).Job).where(
                            __import__("claimbreaker.db", fromlist=["Job"]).Job.case_id == id
                        )
                    )
                ]
                runs = case.result["executions"]
                assert {r["id"] for r in runs} == expected, "Completed runs were repeated"
                assert any(q["id"].startswith("run-context") for q in case.result["questions"])
                assert any(e["source"] in expected for e in case.result["graph"]["edges"])
                payload = case_payload(db, case)
                (root / "after.json").write_text(json.dumps(payload, indent=2))
                (root / "claimbreaker-human-loop.pdf").write_bytes(pdf_report(case))
                (root / "claimbreaker-human-loop.json").write_bytes(json_report(case))
                (root / "claimbreaker-human-loop.zip").write_bytes(
                    evidence_bundle(
                        case, list(db.scalars(select(Artifact).where(Artifact.case_id == id)))
                    )
                )
                summary = {
                    "status": case.status,
                    "baseline": next(
                        r["output"]["metrics"]
                        for r in runs
                        if r["manifest"]["variant"] == "baseline"
                    ),
                    "corrected": next(
                        r["output"]["metrics"]
                        for r in runs
                        if r["manifest"]["variant"] == "grouped"
                    ),
                    "baseline_entities_in_both": next(
                        r["output"]["entity_overlap"]
                        for r in runs
                        if r["manifest"]["variant"] == "baseline"
                    ),
                    "corrected_entities_in_both": next(
                        r["output"]["entity_overlap"]
                        for r in runs
                        if r["manifest"]["variant"] == "grouped"
                    ),
                    "completed_runs_reused_after_restart": True,
                    "execution_question_graph_verified": True,
                    "provider": case.result["provider"],
                    "model": case.result["model"],
                    "history_revisions": len(case.result.get("history", [])),
                }
                (root / "summary.json").write_text(json.dumps(summary, indent=2))
                print(json.dumps(summary), flush=True)
                return
    raise TimeoutError("Case did not settle")


asyncio.run(main())
