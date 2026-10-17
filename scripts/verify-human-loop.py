"""Opt-in real API integration: model, original execution, human correction, cached reuse."""

import asyncio, json
from pathlib import Path
import httpx

BASE = "http://127.0.0.1:8000/api/v1"


async def settle(client, id):
    last = None
    for _ in range(180):
        c = (await client.get(f"{BASE}/cases/{id}")).json()
        if c["status"] != last:
            print(json.dumps({"stage": c["status"], "case_id": id}), flush=True)
            last = c["status"]
        if c["status"] in {
            "review_ready",
            "partially_complete",
            "awaiting_input",
            "failed",
            "cancelled",
        }:
            assert c["status"] not in {"failed", "cancelled"}, c.get("jobs")
            return c
        await asyncio.sleep(4)
    raise RuntimeError("Case did not settle")


async def main():
    root = Path("tmp/human-loop-acceptance")
    root.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=120) as client:
        c = (
            await client.post(
                BASE + "/cases",
                json={
                    "title": "Live human-loop acceptance — synthetic cohort",
                    "provider": "openai",
                },
            )
        ).json()
        id = c["id"]
        response = await client.post(f"{BASE}/cases/{id}/sample/leakage")
        response.raise_for_status()
        before = await settle(client, id)
        (root / "before.json").write_text(json.dumps(before, indent=2))
        baseline = [
            r
            for r in before["result"].get("executions", [])
            if r["status"] == "completed" and r["manifest"]["variant"] == "baseline"
        ]
        assert baseline, "No completed measured baseline"
        response = await client.post(
            f"{BASE}/cases/{id}/decisions",
            json={
                "question_id": "generalization",
                "answer": "new_entities",
                "rationale": "The synthetic fixture explicitly models deployment on previously unseen people.",
            },
        )
        response.raise_for_status()
        after = await settle(client, id)
        (root / "after.json").write_text(json.dumps(after, indent=2))
        runs = after["result"]["executions"]
        group = next(
            r for r in runs if r["status"] == "completed" and r["manifest"]["variant"] == "grouped"
        )
        reused = next(r for r in runs if r["manifest"]["variant"] == "baseline")
        assert baseline[0]["id"] == reused["id"], "Completed baseline was unnecessarily repeated"
        assert group["output"]["entity_overlap"] == 0 and reused["output"]["entity_overlap"] > 0
        assert (
            group["manifest"]["classification"] == "corrected_protocol"
            and reused["manifest"]["classification"] == "original_execution"
        )
        for ext in ["json", "pdf", "zip"]:
            r = await client.get(f"{BASE}/cases/{id}/exports/{ext}")
            r.raise_for_status()
            (root / f"claimbreaker-human-loop.{ext}").write_bytes(r.content)
        summary = {
            "baseline": reused["output"]["metrics"],
            "corrected": group["output"]["metrics"],
            "baseline_entities_in_both": reused["output"]["entity_overlap"],
            "corrected_entities_in_both": group["output"]["entity_overlap"],
            "completed_baseline_reused": True,
            "model": after["result"].get("model"),
            "provider": after["result"]["provider"],
            "history_revisions": len(after["result"].get("history", [])),
        }
        (root / "summary.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary), flush=True)


asyncio.run(main())
