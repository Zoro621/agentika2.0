from types import SimpleNamespace
from claimbreaker.parsing import parse, code_profile
from claimbreaker.checks import extract_claims, compare_metrics, methodology
from claimbreaker.additional_checks import arithmetic_checks
from claimbreaker.providers import strict_schema
from claimbreaker.schemas import ClaimBatch
import json
import pytest


def art(id, path, kind, body):
    a = SimpleNamespace(id=id, path=path, kind=kind)
    return {"id": id, "path": path, "kind": kind, "parsed": parse(a, body.encode())}


def test_rounding_not_flagged():
    a = art(
        "p", "paper.md", "documentation", "Accuracy: 91.2% (dataset=cohort split=test model=rf)"
    )
    b = art(
        "r",
        "results.json",
        "results",
        json.dumps({"accuracy": 0.9124, "dataset": "cohort", "split": "test", "model": "rf"}),
    )
    findings, checks = compare_metrics([a, b], extract_claims([a, b]), [])
    assert not findings
    assert checks[0]["status"] == "passed"


def test_version_gate_and_context():
    a = art(
        "p", "paper.md", "documentation", "Accuracy: 97.5% (dataset=cohort split=test model=rf)"
    )
    b = art(
        "r",
        "results.json",
        "results",
        json.dumps({"accuracy": 0.84, "dataset": "cohort", "split": "test", "model": "rf"}),
    )
    claims = extract_claims([a, b])
    f, _ = compare_metrics([a, b], claims, [])
    assert f[0]["evidence_status"] == "supported_concern"
    f, _ = compare_metrics(
        [a, b], claims, [{"question_id": "repository-version", "answer": "same"}]
    )
    assert f[0]["evidence_status"] == "verified_artifact_discrepancy"


def test_different_split_is_inconclusive():
    a = art(
        "p",
        "paper.md",
        "documentation",
        "Accuracy: 97.5% (dataset=cohort split=validation model=rf)",
    )
    b = art(
        "r",
        "results.json",
        "results",
        json.dumps({"accuracy": 0.84, "dataset": "cohort", "split": "test", "model": "rf"}),
    )
    f, c = compare_metrics([a, b], extract_claims([a, b]), [])
    assert not f and c[0]["status"] == "inconclusive"


def test_no_cherry_picking():
    a = art(
        "p", "paper.md", "documentation", "Accuracy: 97.5% (dataset=cohort split=test model=rf)"
    )
    b = art(
        "r",
        "results.json",
        "results",
        json.dumps(
            {
                "runs": [{"accuracy": 0.84}, {"accuracy": 0.975}],
                "dataset": "cohort",
                "split": "test",
                "model": "rf",
            }
        ),
    )
    f, c = compare_metrics([a, b], extract_claims([a, b]), [])
    assert not f and c[0]["status"] == "inconclusive"


def test_preprocessing_and_explicit_target():
    p = code_profile(
        'import pandas as pd\ndata = pd.read_csv("data.csv")\nX = data[["age", "signal"]]\ny = data["outcome"]\nX = scaler.fit_transform(X)\ntrain_test_split(X, y, random_state=42)\nmodel = LogisticRegression(C=1)'
    )
    assert p["target"] == "outcome" and p["features"] == ["age", "signal"]
    assert p["preprocessing_before_split"]


def test_grouping_question_is_semantic():
    a = art("d", "cohort.csv", "data", "person_id,signal,outcome\n1,2,0\n1,3,0\n2,2,1\n2,3,1\n")
    b = art("c", "train.py", "code", "train_test_split(X, y)\n")
    f, _, q = methodology([a, b], [])
    assert f[0]["evidence_status"] == "candidate" and q[0]["id"] == "generalization"
    f, _, q = methodology([a, b], [{"question_id": "generalization", "answer": "known_entities"}])
    assert not f and q[0]["answer"] == "known_entities"


def test_confusion_matrix_recomputed():
    a = art(
        "r",
        "results.json",
        "results",
        json.dumps({"accuracy": 0.95, "confusion_matrix": [[40, 10], [10, 40]]}),
    )
    f, c = arithmetic_checks([a], [])
    assert f[0]["observed"]["artifact"] == 0.8
    assert c[0]["status"] == "flagged"


@pytest.mark.parametrize(
    "record",
    [
        {"accuracy": 0.95, "confusion_matrix": [[0.8, 0.2], [0.1, 0.9]]},
        {"accuracy": 0.95, "confusion_matrix": [[1, 0], [0, 1]], "normalized": True},
        {"accuracy": 0.95, "confusion_matrix": [[1, 0], [0, 1]], "normalize": "true"},
        {"accuracy": 0.95, "confusion_matrix": [[40, 10], [10, 40]], "weighted": True},
    ],
)
def test_unsupported_confusion_matrix_cannot_verify_contradiction(record):
    a = art("r", "results.json", "results", json.dumps(record))
    findings, checks = arithmetic_checks([a], [])
    assert not findings
    assert checks[0]["status"] == "inconclusive"


def test_confusion_matrix_respects_recorded_accuracy_precision():
    a = art(
        "r",
        "results.json",
        "results",
        json.dumps({"accuracy": 0.83, "confusion_matrix": [[5, 1], [1, 5]]}),
    )
    findings, checks = arithmetic_checks([a], [])
    assert not findings and checks[0]["status"] == "passed"


def test_model_schema_is_closed():
    schema = strict_schema(ClaimBatch.model_json_schema())
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["ExtractedClaim"]["additionalProperties"] is False
