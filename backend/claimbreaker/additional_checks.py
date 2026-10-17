"""Arithmetic checks only when inputs establish the same quantity."""

import json
import math
import re
from decimal import Decimal
from .checks import finding, stable


def arithmetic_checks(artifacts, claims):
    findings, checks = [], []
    for artifact in artifacts:
        structured = artifact["parsed"].get("structured")
        if isinstance(structured, dict):
            matrix = structured.get("confusion_matrix")
            metric = structured.get("accuracy")
            if (
                isinstance(matrix, list)
                and type(metric) in (float, int)
                and math.isfinite(metric)
                and 0 <= metric <= 1
            ):
                try:
                    normalization = [
                        structured[k]
                        for k in ("normalized", "normalize", "normalization", "matrix_normalized")
                        if k in structured
                    ]
                    if any(v is not None and v is not False and v != "none" for v in normalization):
                        raise ValueError()
                    if structured.get("weighted") or structured.get("sample_weight") is not None:
                        raise ValueError()
                    if not matrix or any(len(row) != len(matrix) for row in matrix):
                        raise ValueError()
                    # Normalized/weighted matrices do not establish class supports.
                    # Require actual observation counts before deriving overall accuracy.
                    if any(type(x) is not int or x < 0 for row in matrix for x in row):
                        raise ValueError()
                    total = sum(sum(row) for row in matrix)
                    if total <= 0:
                        raise ValueError()
                    computed = sum(matrix[i][i] for i in range(len(matrix))) / total
                    decimals = max(0, -Decimal(str(metric)).as_tuple().exponent)
                    tolerance = 0.5 * 10**-decimals if decimals else 1e-9
                    agrees = math.isclose(computed, metric, rel_tol=0, abs_tol=tolerance + 1e-10)
                    checks.append(
                        {
                            "id": stable("check", artifact["id"] + "confusion"),
                            "name": "Accuracy ↔ confusion matrix",
                            "status": "passed" if agrees else "flagged",
                            "detail": f"Matrix accuracy {computed:.6g}; recorded accuracy {metric:.6g}",
                        }
                    )
                    if not agrees:
                        e = {
                            "id": artifact["id"] + ":confusion",
                            "artifact_id": artifact["id"],
                            "path": artifact["path"],
                            "pointer": "/confusion_matrix",
                            "text": json.dumps(
                                {"confusion_matrix": matrix, "accuracy": metric}, indent=2
                            ),
                        }
                        findings.append(
                            finding(
                                "Recorded accuracy does not match its confusion matrix",
                                "artifact_arithmetic",
                                "verified_internal_inconsistency",
                                "high",
                                "Accuracy recomputed from the same result record's confusion matrix differs from the recorded accuracy.",
                                [e],
                                {"reported": metric, "artifact": computed, "metric": "accuracy"},
                                [
                                    "The record could combine outputs from different evaluation contexts"
                                ],
                                next_action="Verify that the matrix and metric represent the same evaluation.",
                            )
                        )
                except (ValueError, TypeError, IndexError):
                    checks.append(
                        {
                            "id": stable("check", artifact["id"] + "confusion"),
                            "name": "Accuracy ↔ confusion matrix",
                            "status": "inconclusive",
                            "detail": "Accuracy requires a square matrix of nonnegative integer observation counts. Normalized, weighted, or otherwise unsupported matrices remain inconclusive.",
                        }
                    )
            keys = ("n_samples", "train_samples", "test_samples")
            if all(isinstance(structured.get(k), int) and structured[k] >= 0 for k in keys):
                n, train, test = (structured[k] for k in keys)
                agrees = n == train + test
                checks.append(
                    {
                        "id": stable("check", artifact["id"] + "counts"),
                        "name": "Sample-count reconciliation",
                        "status": "passed" if agrees else "flagged",
                        "detail": f"Total {n}; training + test {train + test}",
                    }
                )
                if not agrees:
                    e = {
                        "id": artifact["id"] + ":counts",
                        "artifact_id": artifact["id"],
                        "path": artifact["path"],
                        "pointer": "/n_samples",
                        "text": json.dumps({k: structured[k] for k in keys}),
                    }
                    findings.append(
                        finding(
                            "Declared sample counts do not reconcile",
                            "sample_count",
                            "supported_concern",
                            "medium",
                            "The recorded total is different from training plus test samples.",
                            [e],
                            alternatives=[
                                "A validation, excluded, or unassigned subset may account for the difference"
                            ],
                            limitations=[
                                "The dataset partition convention must be established before calling this an error"
                            ],
                        )
                    )
        if artifact["kind"] in {"paper", "documentation"}:
            for source in artifact["parsed"].get("anchors", []):
                pattern = r"from\s+(\d+(?:\.\d+)?)%\s+to\s+(\d+(?:\.\d+)?)%[^\n.]{0,70}?relative improvement\s*[:=]?\s*(\d+(?:\.\d+)?)%"
                for m in re.finditer(pattern, source["text"], re.I):
                    before, after, reported = map(float, m.groups())
                    if before <= 0:
                        continue
                    computed = (after - before) / before * 100
                    precision = len(m.group(3).split(".")[1]) if "." in m.group(3) else 0
                    tolerance = 0.5 * 10**-precision
                    agrees = abs(computed - reported) <= tolerance
                    checks.append(
                        {
                            "id": stable("check", source["id"] + m.group(0)),
                            "name": "Relative improvement arithmetic",
                            "status": "passed" if agrees else "flagged",
                            "detail": f"Reported {reported}%; recomputed {computed:.6g}%",
                        }
                    )
                    if not agrees:
                        findings.append(
                            finding(
                                "Relative improvement arithmetic differs from the stated endpoints",
                                "paper_arithmetic",
                                "supported_concern",
                                "medium",
                                "The explicitly labeled relative improvement does not match the stated start and end percentages within reported precision.",
                                [source],
                                {
                                    "reported_relative_percent": reported,
                                    "computed_relative_percent": computed,
                                },
                                limitations=[
                                    "Endpoint rounding and surrounding experimental context still require review"
                                ],
                            )
                        )
    numeric = [c for c in claims if c.get("metric") and c.get("value") is not None]
    if numeric and not any(a["kind"] == "results" for a in artifacts):
        checks.append(
            {
                "id": "missing-result-artifacts",
                "name": "Result-artifact availability",
                "status": "inconclusive",
                "detail": "Numerical claims were found, but no saved result artifacts were supplied. Absence is a reproducibility gap, not a contradiction.",
            }
        )
    return findings, checks
