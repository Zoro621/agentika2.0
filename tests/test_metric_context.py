import json
from types import SimpleNamespace
from claimbreaker.parsing import parse
from claimbreaker.checks import extract_claims, compare_metrics


def art(id, path, kind, body):
    return {
        "id": id,
        "path": path,
        "kind": kind,
        "parsed": parse(SimpleNamespace(id=id, path=path, kind=kind), body.encode()),
    }


def test_explicit_percent_unit_is_normalized():
    p = art(
        "p", "paper.md", "documentation", "Accuracy: 91.2% (dataset=cohort split=test model=rf)"
    )
    r = art(
        "r",
        "results.json",
        "results",
        json.dumps(
            {
                "dataset": "cohort",
                "split": "test",
                "model": "rf",
                "accuracy": 91.2,
                "units": "percent",
            }
        ),
    )
    f, c = compare_metrics([p, r], extract_claims([p]), [])
    assert not f and c[0]["status"] == "passed"


def test_macro_micro_are_not_interchanged():
    p = art(
        "p", "paper.md", "documentation", "Macro F1: 91.2% (dataset=cohort split=test model=rf)"
    )
    r = art(
        "r",
        "results.json",
        "results",
        json.dumps({"dataset": "cohort", "split": "test", "model": "rf", "f1_micro": 0.87}),
    )
    f, c = compare_metrics([p, r], extract_claims([p]), [])
    assert not f and c[0]["status"] == "inconclusive" and "averaging" in c[0]["detail"]


def test_integer_seed_context_is_not_lost():
    p = art("p", "paper.md", "documentation", "Accuracy: 91.2% (dataset=cohort seed=42)")
    r = art(
        "r",
        "results.json",
        "results",
        json.dumps({"dataset": "cohort", "seed": 99, "accuracy": 0.8}),
    )
    f, c = compare_metrics([p, r], extract_claims([p]), [])
    assert not f and "seed" in c[0]["detail"]


def test_mean_and_best_results_are_not_interchanged():
    p = art(
        "p",
        "paper.md",
        "documentation",
        "Mean accuracy: 91.2% (dataset=cohort split=test model=rf)",
    )
    r = art(
        "r",
        "results.json",
        "results",
        json.dumps(
            {
                "accuracy": 0.97,
                "aggregation": "best",
                "dataset": "cohort",
                "split": "test",
                "model": "rf",
            }
        ),
    )
    f, c = compare_metrics(
        [p, r], extract_claims([p]), [{"question_id": "repository-version", "answer": "same"}]
    )
    assert not f and "aggregation" in c[0]["detail"]


def test_different_source_version_changes_the_verdict():
    p = art("p", "paper.md", "documentation", "Accuracy: 91.2% (dataset=cohort)")
    r = art("r", "results.json", "results", json.dumps({"accuracy": 0.8, "dataset": "cohort"}))
    f, c = compare_metrics(
        [p, r], extract_claims([p]), [{"question_id": "repository-version", "answer": "different"}]
    )
    assert f[0]["evidence_status"] == "inconclusive" and f[0]["impact"] == "informational"


def test_negative_r2_and_leading_decimal_are_parsed_without_scale_guessing():
    p = art("p", "paper.md", "documentation", "R2: -0.25\nAccuracy: .912 (dataset=cohort)")
    claims = extract_claims([p])
    assert {c["value"] for c in claims} == {-0.25, 0.912}
