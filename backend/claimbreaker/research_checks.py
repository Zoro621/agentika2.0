"""Traceable partition, chronology and explicit source data-flow checks."""

import re
from .checks import finding, stable, at_line


def expanded_checks(artifacts, decisions):
    findings, checks, questions = [], [], []
    answers = {d["question_id"]: d["answer"] for d in decisions}
    partitions = []
    for a in artifacts:
        profile = a["parsed"].get("profile", {})
        for label, hashes in profile.get("partition_hashes", {}).items():
            partitions.append((a, label, set(hashes), profile.get("fingerprint_columns")))
        if not profile.get("partition_hashes"):
            match = re.search(
                r"(?:^|[/_.-])(train|test|validation|valid)(?:[/_.-]|$)", a["path"], re.I
            )
            if match and profile.get("row_hashes"):
                partitions.append(
                    (
                        a,
                        match[1].lower(),
                        set(profile["row_hashes"]),
                        profile["fingerprint_columns"],
                    )
                )
    for i, (left, role, hashes, columns) in enumerate(partitions):
        for right, other, remaining, other_columns in partitions[i + 1 :]:
            if (role == "train") == (other == "train") or columns != other_columns:
                continue
            overlap = hashes & remaining
            sampled = left["parsed"]["profile"].get("fingerprint_sampled") or right["parsed"][
                "profile"
            ].get("fingerprint_sampled")
            evidence = left["parsed"]["anchors"][:1] + right["parsed"]["anchors"][:1]
            checks.append(
                {
                    "id": stable("check", left["id"] + role + right["id"] + other),
                    "name": "Observation overlap across declared partitions",
                    "status": "flagged" if overlap else "inconclusive" if sampled else "passed",
                    "detail": f"{len(overlap)} identical observation fingerprints across {role} and {other}; {'bounded sample' if sampled else 'all profiled rows'}.",
                }
            )
            if overlap:
                findings.append(
                    finding(
                        "Identical observations occur across declared evaluation partitions",
                        "partition_overlap",
                        "supported_concern",
                        "high",
                        f"{len(overlap)} canonical row fingerprints overlap between declared {role} and {other} partitions with the same columns.",
                        evidence,
                        {"overlap": len(overlap), "columns": columns, "sampled": bool(sampled)},
                        alternatives=[
                            "Repeated observations may be intentional; identifiers and intended independence require review"
                        ],
                        limitations=[
                            "Fingerprints establish identical supplied values, not whether the observations are scientifically independent"
                        ],
                    )
                )
    random = any(a["parsed"].get("code", {}).get("split") == "random" for a in artifacts)
    for a in artifacts:
        code = a["parsed"].get("code", {})
        for flow in code.get("preprocessing_dataflow", []):
            evidence = [at_line(a, flow["fit_line"]), at_line(a, flow["split_line"])]
            if not all(evidence):
                continue
            qid = stable("preprocessing", a["id"])
            if not any(q["id"] == qid for q in questions):
                questions.append(
                    {
                        "id": qid,
                        "title": "Should learned preprocessing use only training observations?",
                        "why": "A supported learned transform was fitted before the split. A revised evaluation must be explicitly distinguished from the original program.",
                        "evidence": evidence,
                        "options": [
                            {
                                "value": "training_only",
                                "label": "Evaluate training-only preprocessing",
                                "effect": "Run a separately labeled correction with the supported pipeline fitted only inside each training split.",
                            },
                            {
                                "value": "as_released",
                                "label": "Inspect the released protocol only",
                                "effect": "Retain the concern and original measurement without changing the protocol.",
                            },
                            {
                                "value": "unknown",
                                "label": "I cannot establish the intended protocol",
                                "effect": "Leave the correction unresolved.",
                            },
                        ],
                        "answer": answers.get(qid),
                    }
                )
            findings.append(
                finding(
                    "A learned transform uses the same feature variable before splitting",
                    "preprocessing_flow",
                    "supported_concern",
                    "high",
                    f"The top-level {flow['variable']} variable is fitted by {flow['transformer']} and then passed to train_test_split without an intervening reassignment.",
                    evidence,
                    alternatives=["Confirm that this code path produced the reported experiment"],
                    limitations=[
                        "This is bounded same-scope AST analysis; runtime control flow and domain context still require review"
                    ],
                )
            )
        for feature in code.get("target_derived_features", []):
            if feature["column"] in (code.get("features") or []) and at_line(a, feature["line"]):
                findings.append(
                    finding(
                        "A selected feature is derived from the target in source",
                        "target_feature",
                        "supported_concern",
                        "high",
                        f"The selected feature {feature['column']} is assigned using target column {feature['depends_on']}.",
                        [at_line(a, feature["line"])],
                        alternatives=["Verify whether this path is training-only diagnostic code"],
                        next_action="Establish feature availability at prediction time, then rerun an approved corrected protocol.",
                    )
                )
        for time in a["parsed"].get("profile", {}).get("time_columns", []):
            if not random:
                continue
            qid = stable("temporal", a["id"] + time["column"])
            questions.append(
                {
                    "id": qid,
                    "title": f"Should evaluation predict future observations using {time['column']}?",
                    "why": "A time-like column and random splitting were found. Temporal deployment is a scientific assumption, not something inferred from the column name alone.",
                    "evidence": a["parsed"]["anchors"][:1],
                    "options": [
                        {
                            "value": "future",
                            "label": "Future observations",
                            "effect": "Use chronological holdout as a corrected protocol; retain the original baseline.",
                        },
                        {
                            "value": "exchangeable",
                            "label": "Exchangeable observations",
                            "effect": "Keep the random split interpretation.",
                        },
                        {
                            "value": "unknown",
                            "label": "I don't know",
                            "effect": "Keep chronology unresolved while independent checks continue.",
                        },
                    ],
                    "answer": answers.get(qid),
                }
            )
            if answers.get(qid) == "future":
                findings.append(
                    finding(
                        "Random splitting differs from the intended future-observation evaluation",
                        "temporal_protocol",
                        "supported_concern",
                        "high",
                        "The researcher established temporal deployment, but the discovered source uses a random row split.",
                        a["parsed"]["anchors"][:1],
                        {"time_column": time["column"]},
                        next_action="Compare the original baseline with the chronological corrected evaluation.",
                    )
                )
    return findings, checks, questions
