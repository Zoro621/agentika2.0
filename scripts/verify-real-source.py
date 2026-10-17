"""Opt-in online smoke check of a published paper and its public repository.

No contradiction is presupposed; this verifies real input parsing and provenance.
"""

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import httpx
from claimbreaker.ingest import fetch_github
from claimbreaker.parser_process import parse_bounded


async def main():
    files, ignored, source = await fetch_github("https://github.com/rasbt/mlxtend", "v0.11.0")
    url = "https://www.theoj.org/joss-papers/joss.00638/10.21105.joss.00638.pdf"
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        response = await client.get(url)
        response.raise_for_status()
    if not response.content.startswith(b"%PDF") or len(response.content) > 25 * 1024**2:
        raise ValueError("Unexpected paper response")
    paper = await parse_bounded(
        SimpleNamespace(id="real-paper", path="joss.00638.pdf", kind="paper"), response.content
    )
    if "MLxtend" not in paper.get("text", ""):
        raise ValueError("Published paper text was not recovered")
    selected = [(path, data) for path, data in files if path.endswith(".py")][:2]
    inspected = []
    for index, (path, data) in enumerate(selected):
        parsed = await parse_bounded(
            SimpleNamespace(id=f"real-code-{index}", path=path, kind="code"), data
        )
        inspected.append(
            {
                "path": path,
                "anchors": len(parsed.get("anchors", [])),
                "warnings": parsed.get("warnings", []),
            }
        )
    result = {
        "repository": source,
        "accepted_artifacts": len(files),
        "ignored": len(ignored),
        "paper": {
            "url": url,
            "sha256": hashlib.sha256(response.content).hexdigest(),
            "pages": paper["pages"],
            "anchors": len(paper["anchors"]),
            "text_extracted": True,
        },
        "inspected_code": inspected,
        "scope": "Real published paper/repository ingestion smoke check. No validity or contradiction judgment.",
    }
    output = Path("tmp/real-source-verification.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
