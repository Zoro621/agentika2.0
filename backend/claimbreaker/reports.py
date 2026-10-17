import io
import json
import zipfile
from html import escape
from datetime import datetime, timezone
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from . import storage


def pdf_report(case):
    data = case.result or {}
    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    font_path = Path(__file__).parent / "assets/fonts/DejaVuSans.ttf"
    if "CBUnicode" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("CBUnicode", str(font_path)))
    for style in styles.byName.values():
        style.fontName = "CBUnicode"
    styles["Title"].fontSize = 22
    styles["Title"].leading = 29
    styles["Heading2"].fontSize = 12
    styles["Heading2"].textColor = colors.HexColor("#176A58")
    styles.add(
        ParagraphStyle(
            name="SmallEvidence",
            fontName="CBUnicode",
            fontSize=8,
            leading=12,
            textColor=colors.HexColor("#465762"),
            spaceAfter=8,
        )
    )
    doc = SimpleDocTemplate(
        stream, pagesize=A4, leftMargin=44, rightMargin=44, topMargin=45, bottomMargin=45
    )
    story = [
        Paragraph("CLAIMBREAKER / EVIDENCE REPORT", styles["Heading2"]),
        Paragraph(escape(case.title), styles["Title"]),
        Paragraph(
            f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} | Revision {case.revision} | {escape(case.status.replace('_', ' '))}",
            styles["SmallEvidence"],
        ),
        Spacer(1, 12),
        Paragraph("Scope and interpretation", styles["Heading2"]),
        Paragraph(
            "This report documents completed checks on the supplied snapshot. A difference is not automatically a contradiction. No scientific misconduct assessment is made. Saved artifacts and reconstructed evaluations are distinguished from independent reproduction.",
            styles["BodyText"],
        ),
        Spacer(1, 12),
    ]
    cov = data.get("coverage", {})
    story.append(
        Paragraph(
            escape(
                f"Analysis provider: {data.get('provider', 'unavailable')} | Model: {data.get('model') or 'No language model used'}"
            ),
            styles["SmallEvidence"],
        )
    )
    for key, val in cov.items():
        story.append(
            Paragraph(f"{escape(key.replace('_', ' ').title())}: {val}", styles["BodyText"])
        )
    story.append(Spacer(1, 16))
    for f in data.get("findings", []):
        story.extend(
            [
                Paragraph(escape(f["title"]), styles["Heading2"]),
                Paragraph(
                    escape(
                        f"Evidence: {f['evidence_status'].replace('_', ' ')} | Review: {f.get('review_status', 'unreviewed')} | Impact: {f['impact']}"
                    ),
                    styles["SmallEvidence"],
                ),
                Paragraph(escape(f["explanation"]), styles["BodyText"]),
                Spacer(1, 8),
            ]
        )
        observed = f.get("observed", {})
        if all(isinstance(observed.get(k), (int, float)) for k in ("reported", "artifact")):
            metric = observed.get("metric", "value")
            percent = metric in {"accuracy", "auc", "f1", "precision", "recall"}
            values = [observed[k] * (100 if percent else 1) for k in ("reported", "artifact")]
            suffix = "%" if percent else ""
            story.append(
                Paragraph(
                    escape(
                        f"Comparable {metric}: stated {values[0]:.6g}{suffix}; artifact/check {values[1]:.6g}{suffix}."
                    ),
                    styles["SmallEvidence"],
                )
            )
        for e in f.get("evidence", []):
            label = e.get("path", "") + (
                f" page {e['page']}"
                if e.get("page")
                else f" line {e['line']}"
                if e.get("line")
                else ""
            )
            story.append(
                Paragraph(
                    escape(label + ": " + e.get("text", "")[:1800]).replace("\n", "<br/>"),
                    styles["SmallEvidence"],
                )
            )
        for limitation in f.get("limitations", []):
            story.append(Paragraph("Limit: " + escape(limitation), styles["SmallEvidence"]))
        for alternative in f.get("alternatives", []):
            story.append(Paragraph("Alternative: " + escape(alternative), styles["SmallEvidence"]))
        story.append(
            Paragraph(
                "Next action: " + escape(f.get("next_action", "Review the source evidence.")),
                styles["SmallEvidence"],
            )
        )
        if f.get("review_note"):
            story.append(
                Paragraph("Reviewer: " + escape(f["review_note"]), styles["SmallEvidence"])
            )
    if not data.get("findings"):
        story.append(
            Paragraph(
                "No discrepancies were identified in the completed checks. This is not a guarantee of overall validity; inspect coverage and skipped checks.",
                styles["BodyText"],
            )
        )
    if data.get("claims"):
        story.extend([Spacer(1, 15), Paragraph("Source claims examined", styles["Heading2"])])
        for claim in data["claims"]:
            anchor = claim.get("anchor", {})
            location = anchor.get("path", "Source") + (
                f" page {anchor['page']}"
                if anchor.get("page")
                else f" line {anchor['line']}"
                if anchor.get("line")
                else ""
            )
            passage = claim["quote"][:600] + (
                " [excerpt; full passage in JSON report]" if len(claim["quote"]) > 600 else ""
            )
            story.append(
                Paragraph(
                    escape(location + " | " + claim.get("type", "claim")), styles["SmallEvidence"]
                )
            )
            story.append(Paragraph(escape(passage), styles["SmallEvidence"]))
    completed = [c for c in data.get("checks", []) if c["status"] in {"passed", "flagged"}]
    if completed:
        story.extend([Spacer(1, 15), Paragraph("Completed checks", styles["Heading2"])])
        for check in completed:
            story.append(
                Paragraph(
                    escape(f"{check['name']} — {check['status']}: {check['detail']}"),
                    styles["SmallEvidence"],
                )
            )
    story.extend([Spacer(1, 15), Paragraph("Experiments", styles["Heading2"])])
    if not data.get("executions"):
        story.append(
            Paragraph(
                "No isolated experiment completed in this revision. Saved results are source evidence, not a new execution.",
                styles["SmallEvidence"],
            )
        )
    for run in data.get("executions", []):
        story.append(
            Paragraph(
                escape(
                    f"{run['manifest'].get('variant', 'Run')}: {run['status']} | {run['manifest'].get('classification', '')}"
                ),
                styles["BodyText"],
            )
        )
        story.append(
            Paragraph(
                escape(
                    f"Run {run['id']} | {run.get('created_at', '')} | input SHA-256 {run['manifest'].get('input_sha256', 'unavailable')}"
                ),
                styles["SmallEvidence"],
            )
        )
        story.append(
            Paragraph(
                escape(json.dumps(run.get("output", {}).get("metrics", {}))),
                styles["SmallEvidence"],
            )
        )
        story.append(
            Paragraph(
                "Environment: " + escape(json.dumps(run.get("output", {}).get("environment", {}))),
                styles["SmallEvidence"],
            )
        )
    story.extend(
        [Spacer(1, 15), Paragraph("Limitations and incomplete checks", styles["Heading2"])]
    )
    for w in data.get("warnings", []):
        story.append(Paragraph(escape(w), styles["SmallEvidence"]))
    for c in data.get("checks", []):
        if c["status"] in {"skipped", "inconclusive"}:
            story.append(Paragraph(escape(c["name"] + ": " + c["detail"]), styles["SmallEvidence"]))
    for q in data.get("questions", []):
        story.append(
            Paragraph(
                escape(q["title"] + " Answer: " + str(q.get("answer") or "Unanswered")),
                styles["SmallEvidence"],
            )
        )
    if case.decisions:
        story.append(Paragraph("Human decision history", styles["Heading2"]))
        for decision in case.decisions:
            story.append(
                Paragraph(
                    escape(
                        f"Revision {decision['revision']}: {decision['question_id']} = {decision['answer']} ({decision['at']})"
                    ),
                    styles["SmallEvidence"],
                )
            )
    for source in case.sources:
        if source.get("commit"):
            story.append(
                Paragraph(
                    escape(f"Repository: {source['url']} | commit: {source['commit']}"),
                    styles["SmallEvidence"],
                )
            )

    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor("#B8D8CE"))
        canvas.line(44, 36, A4[0] - 44, 36)
        canvas.setFont("CBUnicode", 7)
        canvas.setFillColor(colors.HexColor("#6C7C86"))
        canvas.drawString(44, 24, "ClaimBreaker - human-led evidence review")
        canvas.drawRightString(A4[0] - 44, 24, str(doc.page))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()


def json_report(case):
    return json.dumps(
        {
            "case_id": case.id,
            "title": case.title,
            "revision": case.revision,
            "sources": case.sources,
            "decisions": case.decisions,
            "result": case.result,
        },
        indent=2,
        ensure_ascii=False,
    ).encode()


def evidence_bundle(case, artifacts):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.json", json_report(case))
        archive.writestr("report.pdf", pdf_report(case))
        manifest = []
        for a in artifacts:
            archive.writestr("sources/" + a.path, storage.get(a.storage_key))
            manifest.append({"path": a.path, "sha256": a.sha256, "size": a.size})
        archive.writestr(
            "manifest.json",
            json.dumps({"case": case.id, "artifacts": manifest, "sources": case.sources}, indent=2),
        )
        for run in case.result.get("executions", []):
            archive.writestr(
                "runs/" + run["id"] + "/manifest.json", json.dumps(run["manifest"], indent=2)
            )
            archive.writestr(
                "runs/" + run["id"] + "/output.json", json.dumps(run["output"], indent=2)
            )
    return buffer.getvalue()
