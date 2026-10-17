from claimbreaker.review import retain_reviews


def test_reviews_survive_identical_evidence_and_reset_after_interpretation_changes():
    prior = {
        "id": "f",
        "observed": {"accuracy": 0.8},
        "evidence_status": "supported_concern",
        "explanation": "Measured difference",
        "review_status": "accepted",
        "review_note": "Checked sources.",
    }
    unchanged = {**prior, "review_status": "unreviewed", "review_note": ""}
    changed = {**unchanged, "evidence_status": "inconclusive"}
    retain_reviews([unchanged], {"f": prior})
    retain_reviews([changed], {"f": prior})
    assert unchanged["review_status"] == "accepted" and changed["review_status"] == "unreviewed"
