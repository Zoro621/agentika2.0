import json
from types import SimpleNamespace
from claimbreaker.discovery import prioritize
from claimbreaker.parsing import parse
from claimbreaker.checks import extract_claims, compare_metrics, at_line
from claimbreaker.execution import validate_result
import pytest


def test_large_repository_does_not_hide_its_only_dataset():
    files = [
        SimpleNamespace(id=str(i), path=f"tests/helper{i}.py", kind="code", size=100)
        for i in range(150)
    ]
    files += [
        SimpleNamespace(id="data", path="cohort.csv", kind="data", size=100000),
        SimpleNamespace(id="entry", path="run_experiment.py", kind="code", size=20000),
    ]
    chosen = prioritize(files)
    assert (
        len(chosen) == 100
        and any(a.id == "data" for a in chosen)
        and any(a.id == "entry" for a in chosen)
    )


def test_saved_notebook_metric_opens_actual_output_cell():
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "source": ['print("Accuracy: 84.0% (dataset=cohort)")'],
                "outputs": [
                    {"output_type": "stream", "text": ["Accuracy: 84.0% (dataset=cohort)"]}
                ],
            }
        ]
    }
    a = SimpleNamespace(id="nb", path="analysis.ipynb", kind="code")
    parsed = parse(a, json.dumps(notebook).encode())
    repo = {"id": "nb", "path": a.path, "kind": "code", "parsed": parsed}
    paper = {
        "id": "p",
        "path": "paper.md",
        "kind": "documentation",
        "parsed": parse(
            SimpleNamespace(id="p", path="paper.md", kind="documentation"),
            b"Accuracy: 95.0% (dataset=cohort)",
        ),
    }
    findings, _ = compare_metrics([paper, repo], extract_claims([paper]), [])
    assert (
        findings[0]["evidence"][1]["kind"] == "saved_output"
        and findings[0]["evidence"][1]["cell"] == 0
    )


def test_result_discovery_does_not_require_result_filename():
    a = SimpleNamespace(id="x", path="unusual-name.json", kind="data")
    assert parse(a, b'{"accuracy":0.85,"dataset":"cohort"}')["role_hint"] == "results"
    a.path = "unusual.csv"
    assert parse(a, b"y_true,y_pred\n1,1\n0,1\n")["role_hint"] == "results"


def test_stale_runner_measurements_are_rejected():
    with pytest.raises(RuntimeError, match="hash differs"):
        validate_result({"worker_sha256": "an-old-version", "metrics": {"accuracy": 1}}, "data")
