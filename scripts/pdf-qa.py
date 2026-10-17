"""Create/render synthetic fixture and report for visual QA (not user research)."""

import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from claimbreaker.samples import build_sample
from claimbreaker.parsing import parse
from claimbreaker.checks import extract_claims, compare_metrics
from claimbreaker.reports import pdf_report
from pypdf import PdfReader

root = Path("tmp/pdfs/qa")
root.mkdir(parents=True, exist_ok=True)
archive = zipfile.ZipFile(io.BytesIO(build_sample("paper")))
artifacts = []
for index, path in enumerate(("paper.pdf", "results.json")):
    a = SimpleNamespace(
        id=str(index), path=path, kind="paper" if path.endswith(".pdf") else "results"
    )
    artifacts.append(
        {"id": a.id, "path": a.path, "kind": a.kind, "parsed": parse(a, archive.read(path))}
    )
findings, checks = compare_metrics(
    artifacts, extract_claims(artifacts), [{"question_id": "repository-version", "answer": "same"}]
)
unique = {}
for finding in findings:
    if finding["id"] not in unique or finding["evidence_status"].startswith("verified"):
        unique[finding["id"]] = finding
findings = list(unique.values())
case = SimpleNamespace(
    id="qa-synthetic",
    title="Synthetic evidence report",
    revision=1,
    status="partially_complete",
    sources=[{"type": "synthetic_sample"}],
    decisions=[],
    result={
        "findings": findings,
        "checks": checks,
        "warnings": ["Synthetic teaching fixture, not published research."],
        "executions": [],
        "coverage": {"files_inspected": 2, "claims_examined": 2, "checks_completed": 2},
    },
)
(root / "fixture.pdf").write_bytes(archive.read("paper.pdf"))
(root / "report.pdf").write_bytes(pdf_report(case))
for path in (root / "fixture.pdf", root / "report.pdf"):
    reader = PdfReader(path)
    assert all(page.extract_text().strip() for page in reader.pages)
    print(f"{path}: {len(reader.pages)} pages, text extraction verified")
