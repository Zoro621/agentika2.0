"""Readable evidence reports. Conclusions use recorded checks, never a model verdict."""

import io
import json
import math
from collections import Counter
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#142C35")
MUTED = colors.HexColor("#50656D")
TEAL = colors.HexColor("#126B5A")
MINT = colors.HexColor("#70F3C2")
PALE = colors.HexColor("#F1F6F5")
LINE = colors.HexColor("#DCE6E4")
AMBER = colors.HexColor("#946014")
RED = colors.HexColor("#AD4039")
WIDTH = A4[0] - 100
VERIFIED = {
    "verified_internal_inconsistency",
    "verified_artifact_discrepancy",
    "verified_paper_to_artifact_discrepancy",
}
STATUS = {
    "candidate": "Needs investigation",
    "supported_concern": "Evidence-backed concern",
    "verified_internal_inconsistency": "Verified internal inconsistency",
    "verified_artifact_discrepancy": "Verified paper / artifact mismatch",
    "verified_paper_to_artifact_discrepancy": "Verified paper / artifact mismatch",
    "reproduction_difference": "Reproduction differs",
    "no_discrepancy": "No mismatch in this check",
    "no_discrepancy_found": "No mismatch in this check",
    "no_discrepancy_found_in_completed_checks": "No mismatch in completed checks",
    "inconclusive": "Not enough evidence",
}
CLAIM_TYPES = {
    "comparison": "Comparisons",
    "comparative_improvement": "Comparisons",
    "method": "Methods and procedures",
    "evaluation_method": "Methods and procedures",
    "generalization": "Generalization statements",
    "ablation": "Ablation and causal interpretations",
    "numerical": "Numerical results",
    "numerical_result": "Numerical results",
    "sample_count": "Sample and dataset counts",
    "significance": "Statistical significance",
}


def clean(value):
    text = str(value if value is not None else "")
    for dash in "\u2010\u2011\u2012\u2013\u2014\u2212":
        text = text.replace(dash, "-")
    text = text.replace("\ufffd", "[unreadable]")
    return "".join(char for char in text if char >= " " or char in "\n\t")


def label(value):
    return clean(value).replace("_", " ").strip().capitalize()


def metric_value(value):
    # Keep original units: 0.91 is never silently relabeled as 91%.
    if isinstance(value, float) and math.isfinite(value):
        return f"{value:.6g}"
    return clean(value)


def report_summary(data):
    checks = data.get("checks", [])
    completed = sum(c.get("status") in {"passed", "flagged"} for c in checks)
    if not checks:
        completed = data.get("coverage", {}).get("checks_completed", 0)
    findings = [f for f in data.get("findings", []) if not f.get("superseded")]
    verified = sum(f.get("evidence_status") in VERIFIED for f in findings)
    concerns = sum(
        f.get("evidence_status") in {"supported_concern", "candidate", "reproduction_difference"}
        and f.get("review_status") != "dismissed"
        for f in findings
    )
    if verified:
        title, tone = "Discrepancies need your review", RED
        detail = (
            f"{verified} verified discrepancy record(s) are documented in the supplied evidence. "
            "Inspect the source comparisons and alternative explanations before drawing a scientific conclusion."
        )
    elif concerns:
        title, tone = "Concerns need your judgment", AMBER
        detail = (
            f"{concerns} concern(s) need interpretation or further investigation. "
            "These concerns are not established contradictions; the evidence and review state are shown below."
        )
    elif not completed:
        title, tone = "Not enough evidence to verify", AMBER
        detail = (
            "The supplied material was inspected, but no supported checks completed. "
            "Extracting statements does not verify them. This report cannot yet confirm or contradict the research claims."
        )
    else:
        title, tone = "No mismatch in completed checks", TEAL
        detail = (
            f"No verified discrepancy was recorded across {completed} completed check(s). "
            "This conclusion applies only to those checks; unresolved work and unsupported claims remain outside it."
        )
    return {
        "title": title,
        "detail": detail,
        "tone": tone,
        "completed": completed,
        "verified": verified,
        "concerns": concerns,
        "findings": findings,
    }


def pdf_report(case):
    data = case.result or {}
    summary = report_summary(data)
    cov = data.get("coverage", {})
    claims = data.get("claims", [])
    checks = data.get("checks", [])
    runs = data.get("executions", [])
    completed_runs = [r for r in runs if r.get("status") == "completed"]
    questions = data.get("questions", [])
    artifacts = data.get("artifacts", [])
    sources = getattr(case, "sources", []) or []
    decisions = getattr(case, "decisions", []) or []
    if "CBUnicode" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(
            TTFont("CBUnicode", str(Path(__file__).parent / "assets/fonts/DejaVuSans.ttf"))
        )
    styles = {
        "body": ParagraphStyle(
            "Body", fontName="CBUnicode", fontSize=9, leading=14, textColor=INK, spaceAfter=7
        ),
        "small": ParagraphStyle(
            "Small",
            fontName="CBUnicode",
            fontSize=7.5,
            leading=11.5,
            textColor=MUTED,
            spaceAfter=4,
            wordWrap="CJK",
        ),
        "title": ParagraphStyle(
            "Title",
            fontName="Helvetica-Bold",
            fontSize=27,
            leading=31,
            textColor=colors.white,
            spaceAfter=10,
        ),
        "hero": ParagraphStyle(
            "Hero", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=INK, spaceAfter=10
        ),
        "heading": ParagraphStyle(
            "Heading",
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=INK,
            spaceBefore=15,
            spaceAfter=9,
            keepWithNext=True,
        ),
        "sub": ParagraphStyle(
            "Sub",
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=15,
            textColor=INK,
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "eyebrow": ParagraphStyle(
            "Eyebrow",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=12,
            textColor=TEAL,
            spaceAfter=6,
            charSpace=1,
        ),
        "quote": ParagraphStyle(
            "Quote", fontName="CBUnicode", fontSize=8.5, leading=13, textColor=INK, spaceAfter=5
        ),
    }

    def p(text, style="body", **kwargs):
        selected = (
            ParagraphStyle("Custom", parent=styles[style], **kwargs) if kwargs else styles[style]
        )
        return Paragraph(escape(clean(text)).replace("\n", "<br/>"), selected)

    def block(title, body, tone=TEAL, background=PALE):
        table = Table(
            [
                [
                    p(title, "sub", spaceBefore=0, textColor=tone),
                ],
                [p(body)],
            ],
            colWidths=[WIDTH],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), background),
                    ("LINEBEFORE", (0, 0), (0, -1), 3, tone),
                    ("LEFTPADDING", (0, 0), (-1, -1), 14),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                    ("TOPPADDING", (0, 0), (-1, 0), 11),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
                ]
            )
        )
        return KeepTogether([table, Spacer(1, 10)])

    def grid(rows, widths=None, header=True):
        content = [
            [p(cell, "small", textColor=colors.white if header and i == 0 else INK) for cell in row]
            for i, row in enumerate(rows)
        ]
        table = Table(content, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, 0), INK if header else PALE),
                    ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, PALE]),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return table

    def source_location(anchor):
        name = anchor.get("path") or (
            "Run " + str(anchor["execution_id"]) if anchor.get("execution_id") else "Source"
        )
        if anchor.get("page"):
            name += f" | page {anchor['page']}"
        elif anchor.get("line"):
            name += f" | line {anchor['line']}"
        if anchor.get("cell") is not None:
            name += f" | cell {anchor['cell']}"
        if anchor.get("pointer"):
            name += f" | {anchor['pointer']}"
        return name

    def excerpt(text, maximum=1000):
        value = clean(text)
        if len(value) <= maximum:
            return value
        return value[:maximum].rsplit(" ", 1)[0] + " [Excerpt; full text in JSON export.]"

    def bullets(items):
        return "\n".join(f"- {clean(item)}" for item in items)

    def experiment_evidence(evidence):
        try:
            record = json.loads(evidence.get("text", ""))
        except (ValueError, TypeError):
            return None
        if not isinstance(record, dict) or not isinstance(record.get("metrics"), dict):
            return None
        rows = [["Recorded execution evidence", "Value"]]
        if record.get("variant"):
            rows.append(["Evaluation", label(record["variant"])])
        rows.extend([label(k), metric_value(v)] for k, v in record["metrics"].items())
        if record.get("entity_overlap") is not None:
            rows.append(["Individuals shared across train / test", str(record["entity_overlap"])])
        return grid(rows, [WIDTH * 0.65, WIDTH * 0.35])

    story = []
    generated = datetime.now(UTC).strftime("%d %b %Y, %H:%M UTC")
    hero = Table(
        [
            [p("RESEARCH / EVIDENCE REVIEW", "eyebrow", textColor=MINT)],
            [p(case.title, "title")],
            [
                p(
                    f"{generated}   |   Revision {case.revision}   |   {label(case.status)}",
                    "small",
                    textColor=colors.HexColor("#C2D9D4"),
                )
            ],
        ],
        colWidths=[WIDTH],
    )
    hero.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), INK),
                ("LEFTPADDING", (0, 0), (-1, -1), 20),
                ("RIGHTPADDING", (0, 0), (-1, -1), 20),
                ("TOPPADDING", (0, 0), (-1, 0), 19),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 15),
            ]
        )
    )
    story.extend(
        [
            hero,
            Spacer(1, 22),
            p("THE TAKEAWAY", "eyebrow"),
            p(summary["title"], "hero", textColor=summary["tone"]),
            p(summary["detail"]),
            Spacer(1, 12),
        ]
    )
    stats = [
        (
            cov.get("files_inspected", 0),
            "file inspected" if cov.get("files_inspected") == 1 else "files inspected",
        ),
        (cov.get("pdf_pages_inspected", 0), "PDF pages read"),
        (len(claims), "statements extracted"),
        (summary["completed"], "checks completed"),
    ]
    tiles = Table(
        [
            [
                p(str(number), "hero", fontSize=24, leading=27, textColor=TEAL)
                for number, _ in stats
            ],
            [p(name, "small") for _, name in stats],
        ],
        colWidths=[WIDTH / 4] * 4,
    )
    tiles.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, 0), 13),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 12),
            ]
        )
    )
    story.extend([tiles, p("What this means", "heading")])
    if not summary["completed"]:
        story.append(
            p(
                f"{len(claims)} statements were extracted from the supplied material. "
                + (
                    "No isolated experiments completed. "
                    if not completed_runs
                    else f"Completed isolated experiments: {len(completed_runs)}. "
                )
                + "The statements in the appendix are what the source says, "
                "not facts independently confirmed by ClaimBreaker."
            )
        )
    else:
        story.append(
            p(
                f"{summary['completed']} check(s) completed and {len(completed_runs)} isolated experiment(s) finished. "
                "Use the findings to see exactly what was compared. A corrected evaluation changes the protocol; "
                "it is not automatically a reproduction of the paper."
            )
        )
    pending = [q for q in questions if not q.get("answer") or q.get("answer") == "unknown"]
    if pending:
        next_step = pending[0].get("title", "Answer the pending scientific question in the app.")
    elif summary["findings"]:
        next_step = (
            summary["findings"][0].get("next_action")
            or "Inspect the finding and its linked source evidence."
        )
    elif not summary["completed"]:
        next_step = "Add the matching repository or source ZIP, evaluation data and saved results. Then rerun the investigation."
    else:
        next_step = "Review the incomplete checks and confirm that the dataset, metric and evaluation protocol match the paper."
    story.extend(
        [
            block("Your next step", next_step, summary["tone"]),
            p("READING GUIDE", "eyebrow"),
            p(
                "Start with the review and coverage. Use the statement appendix to trace exact quotations back to the source. "
                "The JSON and evidence ZIP retain the full machine-readable records and execution provenance.",
                "small",
            ),
            PageBreak(),
            p("01 / REVIEW", "eyebrow"),
            p("Findings and next steps", "heading"),
        ]
    )

    if not summary["findings"]:
        story.append(
            block(
                "No finding has been established"
                if not summary["completed"]
                else "No verified discrepancy recorded",
                "This is an incomplete investigation, not a clean bill of health. The missing work is listed below."
                if not summary["completed"]
                else "Only the completed checks support this result. The untested statements remain open.",
                summary["tone"],
            )
        )
    for i, finding in enumerate(summary["findings"], 1):
        status = STATUS.get(
            finding.get("evidence_status"), label(finding.get("evidence_status", "unclassified"))
        )
        tone = RED if finding.get("evidence_status") in VERIFIED else AMBER
        story.extend(
            [
                p(f"F{i:02d} / {status.upper()}", "eyebrow", textColor=tone),
                p(finding.get("title", "Finding"), "sub"),
                p(
                    f"Impact: {label(finding.get('impact', 'unspecified'))}   |   Human review: {label(finding.get('review_status', 'unreviewed'))}",
                    "small",
                ),
                p(finding.get("explanation", "No explanation was recorded.")),
            ]
        )
        observed = finding.get("observed") or {}
        if all(isinstance(observed.get(k), (int, float)) for k in ("reported", "artifact")):
            story.append(
                grid(
                    [
                        ["Metric", "Paper / statement", "Artifact / check"],
                        [
                            observed.get("metric", "Value"),
                            metric_value(observed["reported"]),
                            metric_value(observed["artifact"]),
                        ],
                    ],
                    [WIDTH * 0.34, WIDTH * 0.33, WIDTH * 0.33],
                )
            )
            story.append(
                p(
                    "Values retain their recorded scale and units; inspect context before interpreting a difference.",
                    "small",
                )
            )
        for evidence in finding.get("evidence", []):
            formatted = experiment_evidence(evidence)
            story.append(
                KeepTogether(
                    [
                        p(source_location(evidence), "small", textColor=TEAL),
                        formatted
                        if formatted is not None
                        else p(excerpt(evidence.get("text", "")), "quote"),
                        Spacer(1, 6),
                    ]
                )
            )
        for heading, key in [
            ("Other explanations to consider", "alternatives"),
            ("What remains uncertain", "limitations"),
        ]:
            if finding.get(key):
                story.extend([p(heading, "sub"), p(bullets(finding[key]))])
        if finding.get("review_note"):
            story.extend([p("Reviewer note", "sub"), p(finding["review_note"])])
        story.append(
            block("Next action", finding.get("next_action") or "Review the source evidence.", tone)
        )

    story.append(p("What was actually checked", "heading"))
    rows = [
        ["Coverage", "Recorded result"],
        [
            "Files inspected / discovered",
            f"{cov.get('files_inspected', 0)} / {cov.get('files_discovered', 0)}",
        ],
        ["Files unavailable", str(cov.get("files_unavailable", 0))],
        ["PDF pages inspected", str(cov.get("pdf_pages_inspected", 0))],
        ["Statements extracted (not automatically verified)", str(len(claims))],
        ["Completed checks", str(summary["completed"])],
        [
            "Skipped / inconclusive checks",
            str(sum(c.get("status") in {"skipped", "inconclusive"} for c in checks)),
        ],
        ["Completed isolated experiments", str(len(completed_runs))],
        ["Unanswered / uncertain questions", str(len(pending))],
    ]
    story.append(grid(rows, [WIDTH * 0.7, WIDTH * 0.3]))
    if checks:
        story.append(p("Check log", "sub"))
        for check in checks:
            story.extend(
                [
                    p(
                        f"{check.get('name', 'Check')} / {label(check.get('status', 'unknown'))}",
                        "sub",
                    ),
                    p(check.get("detail", "No details recorded.")),
                ]
            )
    if not summary["completed"]:
        story.append(
            block(
                "To make the next investigation useful",
                bullets(
                    [
                        "Attach the paper's corresponding code or a repository ZIP, not only the PDF.",
                        "Include the dataset or evaluation labels/predictions, configurations and saved result files where available.",
                        "Confirm the paper version, dataset and metric definition before comparing quantities.",
                    ]
                ),
            )
        )
    for warning in dict.fromkeys(data.get("warnings", [])):
        story.append(p("Notice: " + warning, "small"))
    if questions:
        story.append(p("Your scientific decisions", "heading"))
        for question in questions:
            answer = question.get("answer")
            option = next((o for o in question.get("options", []) if o.get("value") == answer), {})
            story.append(p(question.get("title", "Question"), "sub"))
            story.append(p(question.get("why", "")))
            story.append(
                p("Answer: " + (option.get("label") or label(answer) if answer else "Not answered"))
            )
            if option.get("effect"):
                story.append(p("What this changes: " + option["effect"]))
    if runs:
        story.extend(
            [
                PageBreak(),
                p("02 / EXPERIMENTS", "eyebrow"),
                p("What the execution measured", "heading"),
                p(
                    "These are recorded run outputs. Original executions and changed-protocol evaluations are labeled separately. "
                    "Matching a paper's result also requires the same data, metric and evaluation conditions."
                ),
            ]
        )
        for i, run in enumerate(runs, 1):
            manifest = run.get("manifest") or {}
            output = run.get("output") or {}
            story.extend(
                [
                    p(f"Run {i:02d}: {label(manifest.get('variant', 'experiment'))}", "sub"),
                    p(
                        f"{label(run.get('status', 'unknown'))} | {label(manifest.get('classification', 'classification unavailable'))}",
                        "small",
                    ),
                ]
            )
            metrics = output.get("metrics", {})
            if metrics:
                story.append(
                    grid(
                        [["Metric (recorded scale)", "Measured value"]]
                        + [[label(k), metric_value(v)] for k, v in metrics.items()],
                        [WIDTH * 0.65, WIDTH * 0.35],
                    )
                )
            else:
                story.append(p("No measured metrics were recorded for this run."))
            if output.get("entity_overlap") is not None:
                story.append(
                    p(f"Individuals shared across train / test: {output['entity_overlap']}")
                )
            story.extend(
                [
                    p("Run ID: " + str(run.get("id", "unavailable")), "small"),
                    p("Recorded at: " + str(run.get("created_at", "unavailable")), "small"),
                    p(
                        "Input SHA-256: " + str(manifest.get("input_sha256", "unavailable")),
                        "small",
                    ),
                ]
            )
            environment = output.get("environment", {})
            if environment:
                story.append(
                    p(
                        "Environment: " + "; ".join(f"{k} {v}" for k, v in environment.items()),
                        "small",
                    )
                )
            for item in output.get("limitations", []):
                story.append(p("Limit: " + str(item), "small"))
            story.append(Spacer(1, 12))

    story.extend(
        [
            PageBreak(),
            p("APPENDIX A / SOURCE STATEMENTS", "eyebrow"),
            p("What the source actually says", "heading"),
            p(
                f"{len(claims)} extracted statement(s). Quotes are source material, not independent validation. "
                "Each entry includes a source location where available. Missing page numbers mean a precise page anchor was not recovered."
            ),
            p(
                "[unreadable] marks an undecodable source character; it has not been guessed or repaired.",
                "small",
            ),
        ]
    )
    grouped = {}
    for i, claim in enumerate(claims, 1):
        group = CLAIM_TYPES.get(claim.get("type"), label(claim.get("type", "other statements")))
        grouped.setdefault(group, []).append((i, claim))
    counts = Counter({group: len(items) for group, items in grouped.items()})
    if counts:
        story.append(
            grid(
                [["Statement category", "Count"]]
                + [[key, str(value)] for key, value in counts.items()],
                [WIDTH * 0.8, WIDTH * 0.2],
            )
        )
    for group, items in grouped.items():
        story.append(p(group, "heading"))
        for number, claim in items:
            anchor = claim.get("anchor") or {}
            quote = claim.get("quote", "No source quotation recorded.")
            content = [
                p(f"C{number:02d}  /  EXTRACTED STATEMENT", "eyebrow"),
                p(excerpt(quote), "quote"),
                p(source_location(anchor), "small", textColor=TEAL),
            ]
            if claim.get("qualifiers"):
                content.append(p("Context: " + str(claim["qualifiers"]), "small"))
            content.append(Spacer(1, 9))
            story.append(KeepTogether(content))
    if not claims:
        story.append(p("No grounded source statements were extracted in this revision."))
    story.extend(
        [
            p("APPENDIX B / AUDIT TRAIL", "eyebrow", spaceBefore=20),
            p("Sources and provenance", "heading"),
            p(f"Case {case.id} | Revision {case.revision}", "small"),
            p(
                f"Analysis provider: {data.get('provider', 'unavailable')} | Model: {data.get('model') or 'No language model used'}",
                "small",
            ),
        ]
    )
    for artifact in artifacts:
        story.append(
            KeepTogether(
                [
                    p(
                        artifact.get("path", "Artifact"),
                        "small",
                        textColor=TEAL,
                        fontSize=8,
                        spaceBefore=3,
                        spaceAfter=2,
                    ),
                    p("SHA-256: " + str(artifact.get("sha256", "unavailable")), "small"),
                ]
            )
        )
    for source in sources:
        if source.get("url"):
            story.append(p("Repository: " + source["url"], "small"))
        if source.get("commit"):
            story.append(p("Pinned commit: " + source["commit"], "small"))
    if decisions:
        story.append(p("Decision history", "sub"))
        for decision in decisions:
            story.append(
                p(
                    f"Revision {decision.get('revision', '?')}: {decision.get('question_id', '?')} = "
                    f"{decision.get('answer', '?')} | {decision.get('at', '')}",
                    "small",
                )
            )
    superseded = [f for f in data.get("findings", []) if f.get("superseded")]
    if superseded:
        story.append(p("Earlier findings replaced by this revision", "sub"))
        for finding in superseded:
            story.append(p(finding.get("title", "Earlier finding"), "small"))
    story.append(
        p(
            "This report documents the supplied snapshot and recorded analysis only. It does not assess scientific misconduct. "
            "Download the JSON export and evidence bundle for full quotations, review records, manifests and logs.",
            "small",
        )
    )

    def furniture(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(TEAL)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(44, A4[1] - 30, "claimbreaker")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(A4[0] - 44, A4[1] - 29, "THE EVIDENCE OBSERVATORY")
        canvas.setStrokeColor(LINE)
        canvas.line(44, 39, A4[0] - 44, 39)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(44, 26, "Human-led research review  /  Evidence before conclusions")
        canvas.drawRightString(A4[0] - 44, 26, f"{str(case.id)[:8]}   /   {doc.page:02d}")
        canvas.restoreState()

    stream = io.BytesIO()
    document = SimpleDocTemplate(
        stream,
        pagesize=A4,
        leftMargin=44,
        rightMargin=44,
        topMargin=52,
        bottomMargin=55,
        title=f"ClaimBreaker | {clean(case.title)}",
        author="ClaimBreaker",
        pageCompression=1,
    )
    document.build(story, onFirstPage=furniture, onLaterPages=furniture)
    return stream.getvalue()
