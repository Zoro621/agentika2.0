from types import SimpleNamespace
from claimbreaker.parsing import parse
from claimbreaker.checks import extract_claims
from claimbreaker.schemas import ClaimBatch
from claimbreaker.claim_validation import merge_claims


def artifact():
    a = SimpleNamespace(id="p", path="paper.md", kind="documentation")
    return {
        "id": a.id,
        "path": a.path,
        "kind": a.kind,
        "parsed": parse(
            a, b"Accuracy: 91.2% on cohort. We evaluated 800 independent participants."
        ),
    }


def test_model_cannot_invent_source_or_measurement():
    a = artifact()
    batch = ClaimBatch.model_validate(
        {
            "claims": [
                {
                    "artifact_id": "unknown",
                    "quote": "Accuracy: 99.9% on cohort.",
                    "type": "numerical",
                    "metric": "accuracy",
                    "value": 0.999,
                },
                {
                    "artifact_id": "p",
                    "quote": "Accuracy: 99.9% on cohort.",
                    "type": "numerical",
                    "metric": "accuracy",
                    "value": 0.999,
                },
                {
                    "artifact_id": "p",
                    "quote": "Accuracy: 91.2% on cohort.",
                    "type": "numerical",
                    "metric": "accuracy",
                    "value": 0.999,
                    "dataset": "cohort",
                },
            ]
        }
    )
    claims = merge_claims([a], extract_claims([a]), batch, "unit-test-provider")
    assert len(claims) == 1 and claims[0]["value"] == 0.912
    assert claims[0]["context"]["dataset"] == "cohort"


def test_contextual_count_does_not_become_a_verified_metric():
    a = artifact()
    batch = ClaimBatch.model_validate(
        {
            "claims": [
                {
                    "artifact_id": "p",
                    "quote": "We evaluated 800 independent participants.",
                    "type": "sample_count",
                    "metric": "accuracy",
                    "value": 0.99,
                }
            ]
        }
    )
    c = merge_claims([a], [], batch, "unit-test-provider")[0]
    assert c["value"] is None and c["metric"] is None and c["anchor"]["text"] == c["quote"]
