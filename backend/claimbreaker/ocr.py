"""Bounded API-assisted OCR with visible provenance and human verification gates."""

from .parser_process import parse_bounded
from .parsing import anchor
from .checks import stable
from .config import settings
import os


async def recover_pages(artifact, data, provider, budget):
    parsed = dict(artifact.parsed)
    recovered = 0
    spent = 0
    if settings().offline or not os.getenv("OPENAI_API_KEY"):
        return parsed, 0
    attempted = list(parsed.get("ocr_attempted", []))
    for detail in parsed.get("page_details", []):
        number = detail["page"]
        if not detail["low_text"] or detail.get("ocr") or spent >= budget:
            continue
        if provider.requested in {"deterministic", "ollama"}:
            break
        attempted.append(number)
        spent += 1
        page = await parse_bounded(artifact, data, operation="render", page=number)
        if not page.get("image"):
            continue
        result = await provider.ocr_page(page["image"])
        if not result or result.unreadable or len(result.text.strip()) < 35:
            continue
        passage = anchor(artifact, result.text, page=number, kind="ocr_passage")
        passage["extraction"] = "api_assisted_ocr"
        parsed["anchors"] = parsed.get("anchors", []) + [passage]
        parsed["text"] = parsed.get("text", "") + "\n\n" + result.text
        parsed["warnings"] = [
            w for w in parsed.get("warnings", []) if not w.startswith(f"Page {number}:")
        ]
        parsed["warnings"].append(
            f"Page {number}: API-assisted OCR; inspect the original image before accepting its quantities"
        )
        detail = {**detail, "ocr": True}
        parsed["page_details"] = [
            detail if d["page"] == number else d for d in parsed["page_details"]
        ]
        recovered += 1
    parsed["ocr_attempted"] = sorted(set(attempted))
    return parsed, spent


def verification_questions(inventory, decisions):
    answers = {d["question_id"]: d["answer"] for d in decisions}
    questions = []
    for artifact in inventory:
        for passage in artifact["parsed"].get("anchors", []):
            if passage.get("kind") != "ocr_passage":
                continue
            qid = stable("ocr", artifact["id"] + str(passage["page"]))
            questions.append(
                {
                    "id": qid,
                    "title": f"Does the recovered text match {artifact['path']} page {passage['page']}?",
                    "why": "Scanned-page extraction is model-assisted. The original page is available for direct inspection; uncertain transcription must not verify a discrepancy.",
                    "evidence": [passage],
                    "options": [
                        {
                            "value": "confirmed",
                            "label": "Matches the original page",
                            "effect": "Permit comparable source checks to use the verified transcription.",
                        },
                        {
                            "value": "incorrect",
                            "label": "Transcription is incorrect",
                            "effect": "Exclude these recovered quantities from discrepancy verification.",
                        },
                        {
                            "value": "unknown",
                            "label": "I cannot verify it",
                            "effect": "Keep the affected checks inconclusive.",
                        },
                    ],
                    "answer": answers.get(qid),
                }
            )
    return questions


def gate_ocr(findings, checks, questions):
    confirmed = {
        q["evidence"][0]["id"]
        for q in questions
        if q["id"].startswith("ocr-") and q.get("answer") == "confirmed"
    }
    for record in [*findings, *checks]:
        uncertain = any(
            e and e.get("kind") == "ocr_passage" and e["id"] not in confirmed
            for e in record.get("evidence", [])
        )
        if not uncertain:
            continue
        if "evidence_status" in record:
            record["evidence_status"] = "inconclusive"
            record["impact"] = "informational"
            record["limitations"] = record.get("limitations", []) + [
                "API-assisted transcription has not been confirmed against the original page"
            ]
        else:
            record["status"] = "inconclusive"
            record["detail"] += " Original scanned-page transcription requires human confirmation."
