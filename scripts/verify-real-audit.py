"""Opt-in full private API audit of a real published paper and pinned repository."""

import asyncio, hashlib, json, time
from pathlib import Path
import httpx

ROOT = Path("tmp/real-paper-audit")
BASE = "http://127.0.0.1:8000/api/v1"
PAPER = "https://www.theoj.org/joss-papers/joss.00638/10.21105.joss.00638.pdf"


async def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=150) as client:
        p = await client.get(PAPER)
        p.raise_for_status()
        response = await client.post(
            BASE + "/cases",
            json={
                "title": "Published-paper validation — MLxtend (JOSS 2018)",
                "provider": "openai",
            },
        )
        response.raise_for_status()
        case = response.json()
        id = case["id"]
        response = await client.post(
            f"{BASE}/cases/{id}/artifacts",
            files={"file": ("joss.00638.pdf", p.content, "application/pdf")},
        )
        response.raise_for_status()
        response = await client.post(
            f"{BASE}/cases/{id}/sources/github",
            json={"url": "https://github.com/rasbt/mlxtend", "ref": "v0.11.0"},
        )
        if response.status_code == 400 and "rate limit" in response.text:
            verified = json.loads(Path("tmp/real-source-verification.json").read_text())[
                "repository"
            ]
            archive = await client.get(
                "https://codeload.github.com/rasbt/mlxtend/zip/" + verified["commit"]
            )
            archive.raise_for_status()
            if len(archive.content) > 50 * 1024**2:
                raise ValueError("Archive budget exceeded")
            import io, zipfile

            original = zipfile.ZipFile(io.BytesIO(archive.content))
            normalized = io.BytesIO()
            with zipfile.ZipFile(normalized, "w", zipfile.ZIP_DEFLATED) as z:
                for member in original.infolist():
                    if not member.is_dir():
                        z.writestr(member.filename.split("/", 1)[1], original.read(member))
            response = await client.post(
                f"{BASE}/cases/{id}/artifacts",
                files={
                    "file": ("mlxtend-pinned-source.zip", normalized.getvalue(), "application/zip")
                },
            )
            response.raise_for_status()
            source = {
                **verified,
                "sha256": hashlib.sha256(archive.content).hexdigest(),
                "acquisition": "Known pinned commit archive uploaded after unauthenticated GitHub API rate limit; tag-to-commit resolution was verified during the prior ingestion test.",
            }
        else:
            response.raise_for_status()
            source = response.json()["source"]
        (ROOT / "provenance.json").write_text(
            json.dumps(
                {
                    "case_id": id,
                    "paper_url": PAPER,
                    "paper_sha256": hashlib.sha256(p.content).hexdigest(),
                    "repository": source,
                    "note": "Public published software paper; no contradiction presupposed. The historical tag is explicitly selected, not assumed to be the publication snapshot.",
                },
                indent=2,
            )
        )
        (ROOT / "paper.pdf").write_bytes(p.content)
        response = await client.post(f"{BASE}/cases/{id}/start")
        response.raise_for_status()
        last = None
        for _ in range(180):
            response = await client.get(f"{BASE}/cases/{id}")
            response.raise_for_status()
            case = response.json()
            if case["status"] != last:
                print(json.dumps({"stage": case["status"], "case_id": id}), flush=True)
                last = case["status"]
            if case["status"] in {
                "review_ready",
                "partially_complete",
                "awaiting_input",
                "failed",
                "cancelled",
            }:
                break
            await asyncio.sleep(4)
        else:
            raise RuntimeError("Real-paper case exceeded polling budget")
        (ROOT / "case.json").write_text(json.dumps(case, indent=2))
        for format in ["json", "pdf", "zip"]:
            response = await client.get(f"{BASE}/cases/{id}/exports/{format}")
            response.raise_for_status()
            (ROOT / f"claimbreaker-real-paper.{format}").write_bytes(response.content)
        ids = {a["id"] for a in case["artifacts"]}
        invalid = [
            e
            for f in case["result"].get("findings", [])
            for e in f.get("evidence", [])
            if e.get("artifact_id") and e["artifact_id"] not in ids
        ]
        if invalid:
            raise AssertionError("A finding referred to an unknown artifact")
        summary = {
            "status": case["status"],
            "provider": case["result"].get("provider"),
            "model": case["result"].get("model"),
            "coverage": case["result"].get("coverage"),
            "claims": len(case["result"].get("claims", [])),
            "findings": [
                {"title": f["title"], "status": f["evidence_status"]}
                for f in case["result"].get("findings", [])
            ],
            "executions": len(case["result"].get("executions", [])),
            "grounded_evidence": not invalid,
            "warnings": case["result"].get("warnings", []),
            "questions": [
                {"title": q["title"], "answer": q.get("answer")}
                for q in case["result"].get("questions", [])
            ],
        }
        (ROOT / "summary.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2), flush=True)


asyncio.run(main())
