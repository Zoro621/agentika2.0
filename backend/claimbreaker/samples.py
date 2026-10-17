"""Reproducible, explicitly synthetic teaching fixtures; scores are computed."""

import io
import json
import zipfile
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.pagesizes import A4
from .sandbox_worker import evaluate

SAMPLES = [
    {
        "id": "leakage",
        "title": "The generalization gap",
        "subtitle": "One question changes the experiment.",
        "tags": ["Entity overlap", "Human judgment"],
        "description": "A synthetic cohort with repeated individuals and a row-level evaluation. Investigate what happens when the intended use is new people.",
    },
    {
        "id": "paper",
        "title": "Follow the published number",
        "subtitle": "A paper, its code, and a different result.",
        "tags": ["Paper ↔ repository", "Saved evidence"],
        "description": "An explicitly synthetic paper contains a deliberately altered reported metric. Trace it to a result computed from the included source and data.",
    },
    {
        "id": "clean",
        "title": "When the evidence holds",
        "subtitle": "Good research deserves a fair hearing.",
        "tags": ["Clean control", "Consistent evidence"],
        "description": "A synthetic experiment with independent entities, training-only preprocessing, and a consistent paper/result pair.",
    },
]


def build_sample(kind):
    if kind not in {x["id"] for x in SAMPLES}:
        raise ValueError("Unknown sample")
    rng = np.random.default_rng(17)
    repeated = kind == "leakage"
    n = 120
    labels = rng.integers(0, 2, n)
    signatures = rng.normal(size=(n, 5))
    if repeated:
        frame = pd.DataFrame(
            np.repeat(signatures, 8, axis=0), columns=[f"signature_{i}" for i in range(5)]
        )
        frame["person_id"] = np.repeat(np.arange(n), 8)
        frame["outcome"] = np.repeat(labels, 8)
    else:
        n = 800
        values = rng.normal(size=(n, 5))
        frame = pd.DataFrame(values, columns=[f"signature_{i}" for i in range(5)])
        frame["person_id"] = np.arange(n)
        frame["outcome"] = (values[:, 0] + 0.6 * values[:, 1] + rng.normal(0, 0.7, n) > 0).astype(
            int
        )
    csv_text = frame.to_csv(index=False)
    features = [f"signature_{i}" for i in range(5)]
    spec = {
        "variant": "baseline",
        "target": "outcome",
        "features": features,
        "estimator": "RandomForestClassifier",
        "params": {"n_estimators": 80, "random_state": 42},
        "seed": 42,
        "test_size": 0.25,
        "entity": "person_id",
        "scaling": False,
        "exclude": [],
    }
    output = evaluate({"csv": csv_text, "spec": spec})
    actual = output["metrics"]["accuracy"]
    reported = round(max(0.01, actual - 0.071), 3) if kind == "paper" else actual
    dataset = "synthetic_cohort"
    code = f"""# SYNTHETIC CLAIMBREAKER DEMO - no real patients or published results.
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
data = pd.read_csv("cohort.csv")
X = data[{features!r}]
y = data["outcome"]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42)
model = RandomForestClassifier(n_estimators=80, random_state=42, n_jobs=1)
model.fit(X_train, y_train)
print("accuracy", accuracy_score(y_test, model.predict(X_test)))
"""
    result = {
        "dataset": dataset,
        "model": "RandomForestClassifier",
        "split": "test",
        "seed": "42",
        "accuracy": actual,
        "artifact_type": "computed synthetic fixture result",
        "provenance": {
            "environment": output["environment"],
            "dataset_sha256": output["dataset_sha256"],
            "train_rows": output["train_rows"],
            "test_rows": output["test_rows"],
        },
    }
    if kind == "paper":
        result.update(
            f1_macro=output["metrics"]["f1_macro"],
            trial_manifest=[{"run": "baseline", "artifact": "results.json"}],
        )
    title = next(s["title"] for s in SAMPLES if s["id"] == kind)
    paragraph = f"Test accuracy: {reported * 100:.3f}% (dataset={dataset} model=RandomForestClassifier split=test seed=42)."
    pdf = io.BytesIO()
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CBLabel",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=colors.HexColor("#168875"),
            spaceAfter=18,
        )
    )
    doc = SimpleDocTemplate(
        pdf, pagesize=A4, rightMargin=48, leftMargin=48, topMargin=45, bottomMargin=45
    )
    story = [
        Paragraph("CLAIMBREAKER / SYNTHETIC DEMO PAPER", styles["CBLabel"]),
        Paragraph(title, styles["Title"]),
        Spacer(1, 12),
        Paragraph(
            "This document is a generated teaching fixture. It is not a published research paper and contains no real participant data.",
            styles["BodyText"],
        ),
        Spacer(1, 22),
        Paragraph("Abstract", styles["Heading2"]),
        Paragraph(
            "We examine a small tabular classification experiment using synthetic observations. The intended deployment population must be established by a researcher before interpreting generalization.",
            styles["BodyText"],
        ),
        Spacer(1, 12),
        Paragraph("Results", styles["Heading2"]),
        Paragraph(paragraph, styles["BodyText"]),
        Spacer(1, 18),
    ]
    table = Table(
        [
            ["Dataset", "Metric", "Reported result"],
            [dataset, "Test accuracy", f"{reported * 100:.3f}%"],
        ],
        colWidths=[210, 110, 130],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#101A24")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("GRID", (0, 1), (-1, -1), 0.4, colors.HexColor("#CCD8DE")),
            ]
        )
    )
    story += [
        table,
        Spacer(1, 22),
        Paragraph("Methods and source correspondence", styles["Heading2"]),
        Paragraph(
            "The released source uses a fixed random seed of 42 and a 25% test partition. The associated result artifact records one computed baseline run. This fixture's paper and repository package are released together.",
            styles["BodyText"],
        ),
        Spacer(1, 12),
        Paragraph("Limitations", styles["Heading2"]),
        Paragraph(
            "Scores describe this synthetic dataset only. A saved result is not an independent reproduction. Repeated observations require a deployment-specific evaluation decision.",
            styles["BodyText"],
        ),
    ]
    if kind == "paper":
        story += [
            Spacer(1, 12),
            Paragraph("Different quantities and released coverage", styles["Heading2"]),
            Paragraph(
                f"Micro F1: {actual * 100:.3f}% (dataset={dataset} model=RandomForestClassifier split=test averaging=micro). The released result contains macro F1. These averaging definitions are different quantities and must not be interchanged. We ran 5 independent trials; only one trial manifest is included in this package.",
                styles["BodyText"],
            ),
            Spacer(1, 12),
            Paragraph("Fixture design note", styles["Heading2"]),
            Paragraph(
                "The reported accuracy was intentionally changed for demonstration. The averaging difference is legitimate. The trial-count statement is a deliberately incomplete-evidence example: only one synthetic baseline was computed and released. None of these statements describe published research.",
                styles["BodyText"],
            ),
        ]
    doc.build(story)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("paper.pdf", pdf.getvalue())
        archive.writestr("train.py", code)
        archive.writestr("cohort.csv", csv_text)
        archive.writestr("results.json", json.dumps(result, indent=2))
        archive.writestr(
            "config.yaml",
            "dataset: synthetic_cohort\nmodel: RandomForestClassifier\nsplit: test\nseed: 42\n",
        )
        archive.writestr(
            "README.md",
            f"# {title}\n\nSYNTHETIC DEMO FIXTURE. Not published research. No real participants.\n\nRead paper.pdf, train.py and results.json together. The experiment target and features are explicit in source.\n",
        )
    return buffer.getvalue()
