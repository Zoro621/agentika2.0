"""Live notebook/CV and container boundary checks; no uploaded program runs on host."""

import asyncio, base64, hashlib, io, json, os, zipfile
from pathlib import Path
import httpx
from claimbreaker.samples import build_sample
from claimbreaker.openai_sandbox import execute, API, destroy
from claimbreaker.execution import validate_result
from claimbreaker.config import settings


async def main():
    source = zipfile.ZipFile(io.BytesIO(build_sample("clean")))
    csv = source.read("cohort.csv").decode()
    code = """import pandas as pd
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.linear_model import LogisticRegression
data = pd.read_csv("cohort.csv")
X = data[["signature_0", "signature_1"]]
y = data["outcome"]
model = LogisticRegression(max_iter=200)
cv = StratifiedKFold(n_splits=4, shuffle=True, random_state=42)
scores = cross_val_score(model, X, y, cv=cv, scoring="accuracy")
print(scores.mean())
"""
    notebook = json.dumps(
        {
            "cells": [
                {
                    "cell_type": "code",
                    "id": "actual-cv",
                    "metadata": {},
                    "outputs": [],
                    "execution_count": None,
                    "source": code.splitlines(True),
                }
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
    ).encode()
    spec = {
        "target": "outcome",
        "features": ["signature_0", "signature_1"],
        "estimator": "LogisticRegression",
        "params": {"max_iter": 200},
        "variant": "baseline",
        "seed": 42,
        "test_size": 0.25,
        "execution_mode": "original",
        "entry_path": "experiment.ipynb",
        "source_files": [
            {"path": "experiment.ipynb", "data": base64.b64encode(notebook).decode()},
            {"path": "cohort.csv", "data": base64.b64encode(csv.encode()).decode()},
        ],
    }
    result = validate_result(await execute({"csv": csv, "spec": spec}), csv)
    assert (
        result["folds"][0]["n_folds"] == 4
        and result["source_hashes"]["experiment.ipynb"] == hashlib.sha256(notebook).hexdigest()
    )
    root = Path("tmp/execution-acceptance")
    root.mkdir(exist_ok=True)
    (root / "notebook-cv.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"notebook_cv": result["folds"], "metrics": result["metrics"]}), flush=True)
    # Separate live isolation checks: scripts/verify-live-boundaries.py


asyncio.run(main())
