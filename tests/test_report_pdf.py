import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from claimbreaker.report_pdf import report_summary
from claimbreaker.reports import pdf_report
from pypdf import PdfReader


def case_with(result, **fields):
    return SimpleNamespace(
        id="report-test",
        title="Research <review>",
        revision=0,
        status="partially_complete",
        result=result,
        sources=[],
        decisions=[],
        **fields,
    )


def test_zero_checks_does_not_present_a_clean_assessment():
    case = case_with(
        {
            "coverage": {"files_inspected": 1, "pdf_pages_inspected": 8},
            "claims": [
                {
                    "quote": "A statement, not a verified fact.",
                    "type": "method",
                    "anchor": {"path": "paper.pdf", "page": 3},
                }
            ],
            "checks": [{"name": "Execution", "status": "skipped", "detail": "Data missing"}],
        }
    )
    pdf = PdfReader(io.BytesIO(pdf_report(case)))
    first = pdf.pages[0].extract_text()
    assert "Not enough evidence to verify" in first
    assert "cannot yet confirm or contradict" in first
    assert "No discrepancies were identified" not in first
    text = "\n".join(page.extract_text() for page in pdf.pages)
    assert "paper.pdf | page 3" in text
    assert "Data missing" in text
    assert "Research <review>" in first


@pytest.mark.parametrize(
    "finding,expected",
    [
        ({"evidence_status": "verified_artifact_discrepancy"}, "Discrepancies need your review"),
        ({"evidence_status": "verified_internal_inconsistency"}, "Discrepancies need your review"),
        ({"evidence_status": "supported_concern"}, "Concerns need your judgment"),
        (
            {"evidence_status": "supported_concern", "superseded": True},
            "No mismatch in completed checks",
        ),
    ],
)
def test_summary_respects_evidence_and_superseded_records(finding, expected):
    result = {"findings": [finding], "checks": [{"status": "passed"}]}
    assert report_summary(result)["title"] == expected


def test_measured_runs_are_readable_and_keep_original_scales():
    fixture = json.loads((Path(__file__).parent / "fixtures/measured-case.json").read_text())
    pdf = PdfReader(io.BytesIO(pdf_report(SimpleNamespace(**fixture))))
    text = "\n".join(page.extract_text() for page in pdf.pages)
    assert "Measured value" in text
    assert "Original execution" in text and "Corrected protocol" in text
    assert "0.5" in text
    assert "Individuals shared across train / test" in text
    assert (
        '"input_sha256"' not in text
    )  # Execution anchors render as labeled tables, not JSON dumps.
    assert fixture["result"]["executions"][0]["manifest"]["input_sha256"] in text
    assert "New individuals" in text


def test_long_quotes_and_unreadable_characters_do_not_break_export():
    quote = "Unclear \ufffd <tag> & a long quotation. " * 80
    result = {"claims": [{"type": "method", "quote": quote, "anchor": {"path": "a.pdf"}}]}
    pdf = PdfReader(io.BytesIO(pdf_report(case_with(result))))
    text = "\n".join(page.extract_text() for page in pdf.pages)
    assert "[unreadable]" in text
    assert "full text in JSON export" in text
    assert "<tag>" in text
