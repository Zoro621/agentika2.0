"""Retain a review only while the evidence and interpretation remain the same."""


def retain_reviews(findings, previous):
    for finding in findings:
        prior = previous.get(finding["id"])
        if prior and all(
            finding.get(k) == prior.get(k) for k in ("observed", "evidence_status", "explanation")
        ):
            finding["review_status"] = prior.get("review_status", "unreviewed")
            finding["review_note"] = prior.get("review_note", "")
