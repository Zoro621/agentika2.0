import json
from .checks import finding, stable


def execution_checks(executions, decisions):
    answers = {d["question_id"]: d["answer"] for d in decisions}
    baseline = next(
        (
            r
            for r in executions
            if r["status"] == "completed" and r["manifest"].get("variant") == "baseline"
        ),
        None,
    )
    grouped = next(
        (
            r
            for r in executions
            if r["status"] == "completed" and r["manifest"].get("variant") == "grouped"
        ),
        None,
    )
    if not baseline or not grouped or answers.get("generalization") != "new_entities":
        return [], []
    if grouped["output"].get("entity_overlap") != 0:
        return [], [
            {
                "id": "grouped-isolation",
                "name": "Entity-separated evaluation",
                "status": "inconclusive",
                "detail": "The corrected run did not establish disjoint entities",
            }
        ]
    check = {
        "id": "grouped-isolation",
        "name": "Entity-separated evaluation",
        "status": "passed",
        "detail": "Corrected evaluation measured zero entity overlap. Results describe a changed protocol, not an independent reproduction.",
    }
    if not baseline["output"].get("entity_overlap"):
        return [], [check]
    evidence = [
        {
            "id": r["id"] + ":output",
            "execution_id": r["id"],
            "path": "Run " + r["id"][:8],
            "kind": "execution",
            "text": json.dumps(
                {
                    "variant": r["manifest"]["variant"],
                    "metrics": r["output"].get("metrics", {}),
                    "entity_overlap": r["output"].get("entity_overlap"),
                    "input_sha256": r["manifest"].get("input_sha256"),
                },
                indent=2,
            ),
        }
        for r in (baseline, grouped)
    ]
    observed = {
        "baseline_metrics": baseline["output"].get("metrics", {}),
        "corrected_metrics": grouped["output"].get("metrics", {}),
        "baseline_entity_overlap": baseline["output"].get("entity_overlap"),
        "corrected_entity_overlap": 0,
    }
    concern = finding(
        "New-individual evaluation changes the evidence boundary",
        "corrected_evaluation",
        "supported_concern",
        "high",
        "You confirmed that deployment concerns new individuals. The measured baseline shared entities across partitions, while the corrected grouped evaluation kept them separate. Inspect the actual metrics and original/reconstructed classification in both manifests.",
        evidence,
        observed,
        ["Group composition and seed variation can also change performance"],
        [
            "The baseline may be original execution or reconstruction, as labeled; the grouped run is an explicitly changed protocol",
            "One corrected split does not establish statistical significance or misconduct",
        ],
        "Review the actual run manifests and evaluate stability across additional group splits before making a broader claim.",
    )
    return [concern], [check]


def paper_execution_checks(claims, executions, decisions):
    """Compare downloaded measurements only after explicit scientific correspondence."""
    answers = {d["question_id"]: d["answer"] for d in decisions}
    findings, checks, questions = [], [], []
    for run in executions:
        if (
            run["status"] != "completed"
            or run["manifest"].get("classification") != "original_execution"
            or run["manifest"].get("variant") != "baseline"
        ):
            continue
        metrics = run["output"].get("metrics", {})
        for claim in [c for c in claims if c.get("metric") and c.get("value") is not None][:12]:
            metric = claim["metric"]
            average = claim.get("context", {}).get("averaging")
            key = (
                metric + "_" + average
                if average and metric in {"f1", "precision", "recall"}
                else metric
            )
            if key not in metrics:
                continue
            observed = metrics[key]
            qid = (
                stable("run-context", claim["id"] + run["fingerprint"])
                if run.get("fingerprint")
                else stable("run-context", claim["id"] + run["id"])
            )
            source = {
                "id": run["id"] + ":measurement:" + key,
                "execution_id": run["id"],
                "path": "Original run " + run["id"][:8],
                "kind": "execution",
                "text": json.dumps(
                    {
                        "metric": key,
                        "value": observed,
                        "manifest": run["manifest"],
                        "environment": run["output"].get("environment"),
                    },
                    indent=2,
                ),
            }
            questions.append(
                {
                    "id": qid,
                    "title": f"Does this original run correspond to the paper’s {key} result?",
                    "why": "Establish paper/repository version, dataset/subset, held-out split, seed/trials, averaging and uncertainty. Matching numbers alone cannot establish correspondence. A corrected protocol is never compared as a reproduction.",
                    "evidence": [claim["anchor"], source],
                    "options": [
                        {
                            "value": "same",
                            "label": "Same experiment, metric and protocol",
                            "effect": "Compare the actual original-run measurement at the paper’s stated precision.",
                        },
                        {
                            "value": "different",
                            "label": "Different experiment or protocol",
                            "effect": "Keep the reproduction comparison inconclusive.",
                        },
                        {
                            "value": "unknown",
                            "label": "I cannot establish that",
                            "effect": "Leave publication comparability unresolved.",
                        },
                    ],
                    "answer": answers.get(qid),
                }
            )
            if answers.get(qid) != "same":
                checks.append(
                    {
                        "id": stable("check", qid),
                        "name": "Paper ↔ original execution",
                        "claim_id": claim["id"],
                        "execution_id": run["id"],
                        "status": "inconclusive",
                        "detail": "A real original-program measurement is available; its scientific correspondence with the paper is unresolved.",
                        "evidence": [claim["anchor"], source],
                    }
                )
                continue
            matches = abs(observed - claim["value"]) <= claim.get("tolerance", 0) + 1e-10
            checks.append(
                {
                    "id": stable("check", qid),
                    "name": "Paper ↔ original execution",
                    "claim_id": claim["id"],
                    "execution_id": run["id"],
                    "status": "passed" if matches else "flagged",
                    "detail": f"Researcher-established corresponding {key}: paper {claim['value']:.8g}, original execution {observed:.8g}.",
                    "evidence": [claim["anchor"], source],
                }
            )
            if not matches:
                findings.append(
                    finding(
                        f"{key.upper()}: original execution differs from the paper",
                        "reproduction",
                        "reproduction_difference",
                        "high",
                        "The immutable original program produced a different metric under researcher-established correspondence. This is a measured reproduction difference; inspect environment, uncertainty, seeds and released inputs before interpreting it as a scientific contradiction.",
                        [claim["anchor"], source],
                        {"metric": key, "reported": claim["value"], "artifact": observed},
                        alternatives=[
                            "Environment/library differences, stochastic variation or incomplete released inputs"
                        ],
                        limitations=[
                            "Scientific correspondence was established by human judgment",
                            "One run does not establish statistical significance or misconduct",
                        ],
                    )
                )
    return findings, checks, questions
