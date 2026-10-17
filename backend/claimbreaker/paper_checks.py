"""Table-cell provenance, declared trial aggregation and bounded narrative arithmetic."""

import json
import re
from statistics import fmean
from .checks import stable, metric_name, compatible, finding


def table_claims(artifact):
    claims = []
    for index, table in enumerate(artifact["parsed"].get("tables", [])):
        rows = table.get("rows", [])
        if len(rows) < 2:
            continue
        header = [str(v or "").strip() for v in rows[0]]
        for row_index, row in enumerate(rows[1:], 1):
            if len(row) != len(header):
                continue
            for column, title in enumerate(header):
                match = re.search(
                    r"\b(accuracy|auc|auroc|f1|precision|recall|rmse|mae|r2)\b", title, re.I
                )
                raw = str(row[column] or "").strip()
                number = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*(%)?", raw)
                if not match or not number:
                    continue
                metric = metric_name(match[1])
                percentage = bool(number[2] or "%" in title)
                value = float(number[1]) / (100 if percentage else 1)
                if (
                    metric in {"accuracy", "auc", "f1", "precision", "recall"}
                    and not 0 <= value <= 1
                ):
                    continue
                precision = len(number[1].split(".")[1]) if "." in number[1] else 0
                context = {}
                model_col = next(
                    (
                        i
                        for i, h in enumerate(header)
                        if h.lower() in {"model", "method", "classifier", "algorithm"}
                    ),
                    None,
                )
                if model_col is not None:
                    context["model"] = str(row[model_col])
                for average in ("macro", "micro", "weighted"):
                    if average in title.lower():
                        context["averaging"] = average
                quote = json.dumps({"headers": header, "row": row}, ensure_ascii=False)
                source = {
                    "id": f"{artifact['id']}:table:{index}:row:{row_index}",
                    "artifact_id": artifact["id"],
                    "path": artifact["path"],
                    "page": table["page"],
                    "bbox": table["bbox"],
                    "text": quote,
                    "kind": "table_cell",
                    "row": row_index,
                    "column": column,
                }
                claims.append(
                    {
                        "id": stable("claim", source["id"] + title),
                        "artifact_id": artifact["id"],
                        "quote": quote,
                        "type": "numerical",
                        "metric": metric,
                        "value": value,
                        "reported": f"{title}: {raw}",
                        "tolerance": 0.5 * 10**-precision / (100 if percentage else 1),
                        "units": "fraction"
                        if metric in {"accuracy", "auc", "f1", "precision", "recall"}
                        else "reported scale",
                        "context": context,
                        "anchor": source,
                        "origin": "deterministic extracted table cell; inspect rendered source region",
                    }
                )
    return claims


def extended_paper_checks(inventory, claims, decisions):
    answers = {d["question_id"]: d["answer"] for d in decisions}
    findings, checks, questions, handled = [], [], [], set()
    for claim in claims:
        if not claim.get("metric") or claim.get("value") is None:
            continue
        records = []
        for artifact in inventory:
            if artifact["kind"] != "results" and not artifact["parsed"].get("saved_outputs"):
                continue
            for number in artifact["parsed"].get("numbers", []):
                if metric_name(number["key"]) != claim["metric"] or compatible(
                    claim.get("context", {}), number.get("context", {})
                ):
                    continue
                value = number["value"]
                units = str(number.get("context", {}).get("units", "")).lower()
                if "%" in units or "percent" in units:
                    value /= 100
                if (
                    claim["metric"] in {"accuracy", "auc", "f1", "precision", "recall"}
                    and not 0 <= value <= 1
                ):
                    continue
                records.append((artifact, number, value))
        if len(records) < 2:
            continue
        # Explicitly incompatible result populations never become commensurate through aggregation.
        if any(
            len(
                {
                    str(n.get("context", {}).get(k))
                    for _, n, _ in records
                    if n.get("context", {}).get(k) is not None
                }
            )
            > 1
            for k in ("dataset", "model", "split", "population", "subset", "averaging", "version")
        ):
            continue
        handled.add(claim["id"])
        qid = "aggregation:" + claim["id"]
        questions.append(
            {
                "id": qid,
                "title": f"How do the {len(records)} released {claim['metric']} records correspond to this claim?",
                "why": "Multiple results are available. An individual trial must not be cherry-picked. Establish that they are comparable trials and the intended summary.",
                "evidence": [claim["anchor"]],
                "options": [
                    {
                        "value": "mean",
                        "label": "Comparable trials — report the mean",
                        "effect": "Compute the arithmetic mean of the compatible released records and compare at the claim's reported precision.",
                    },
                    {
                        "value": "best",
                        "label": "Comparable trials — report the best run",
                        "effect": "Compute the appropriate best value (lower for RMSE/MAE); retain this researcher-established selection rule.",
                    },
                    {
                        "value": "different",
                        "label": "These are not comparable trials",
                        "effect": "Keep this comparison inconclusive.",
                    },
                    {
                        "value": "unknown",
                        "label": "I cannot establish that",
                        "effect": "Keep aggregation and correspondence unresolved.",
                    },
                ],
                "answer": answers.get(qid),
            }
        )
        mode = answers.get(qid)
        if mode not in {"mean", "best"}:
            checks.append(
                {
                    "id": stable("check", qid),
                    "name": "Trial-aware metric comparison",
                    "status": "inconclusive",
                    "detail": f"{len(records)} released values require a researcher-established trial/aggregation interpretation",
                    "claim_id": claim["id"],
                }
            )
            continue
        explicit = claim.get("context", {}).get("aggregation")
        if explicit and explicit != mode:
            checks.append(
                {
                    "id": stable("check", qid),
                    "name": "Trial-aware metric comparison",
                    "status": "inconclusive",
                    "detail": "The researcher-selected aggregation differs from the paper's explicit aggregation; resolve this context before comparison",
                    "claim_id": claim["id"],
                }
            )
            continue
        values = [value for _, _, value in records]
        observed = (
            fmean(values)
            if mode == "mean"
            else min(values)
            if claim["metric"] in {"rmse", "mae"}
            else max(values)
        )
        matches = abs(observed - claim["value"]) <= claim.get("tolerance", 0) + 1e-10
        evidence = [claim["anchor"]] + [
            {
                "id": a["id"] + n["pointer"],
                "artifact_id": a["id"],
                "path": a["path"],
                "pointer": n["pointer"],
                "kind": "result",
                "text": f"{n['pointer']}: {n['value']}\nContext: {n.get('context', {})}",
            }
            for a, n, _ in records[:12]
        ]
        checks.append(
            {
                "id": stable("check", qid),
                "name": "Trial-aware metric comparison",
                "status": "passed" if matches else "flagged",
                "detail": f"Researcher-established {mode} of {len(values)} released trials: {observed:.8g}; paper {claim['value']:.8g}",
                "claim_id": claim["id"],
                "evidence": evidence,
            }
        )
        if not matches:
            findings.append(
                finding(
                    f"{claim['metric'].upper()}: paper differs from the established trial summary",
                    "paper_repository",
                    "verified_artifact_discrepancy"
                    if answers.get("repository-version") == "same"
                    else "supported_concern",
                    "high",
                    "The declared researcher-established summary was computed from the released values. This compares saved artifacts; it is not an independent reproduction.",
                    evidence,
                    {
                        "metric": claim["metric"],
                        "reported": claim["value"],
                        "artifact": observed,
                        "aggregation": mode,
                        "trials": len(values),
                    },
                    alternatives=[
                        "An incomplete released trial set or a different paper/repository version"
                    ],
                    limitations=[
                        "Trial comparability and aggregation were established by human judgment"
                    ],
                )
            )
    for artifact in inventory:
        if artifact["kind"] not in {"paper", "documentation"}:
            continue
        for source in artifact["parsed"].get("anchors", []):
            text = source["text"]
            patterns = {
                "total": r"(?:cohort|dataset|study)\s+(?:contains|included|comprised|has|of)\s+([\d,]+)\s+(?:participants|samples|instances|observations)",
                "train": r"([\d,]+)\s+training\s+(?:participants|samples|instances|observations)",
                "test": r"([\d,]+)\s+(?:test|testing)\s+(?:participants|samples|instances|observations)",
            }
            counts = {
                k: [int(v.replace(",", "")) for v in re.findall(p, text, re.I)]
                for k, p in patterns.items()
            }
            if not all(len(values) == 1 for values in counts.values()):
                continue
            total, train, test = (counts[k][0] for k in ("total", "train", "test"))
            matches = total == train + test
            checks.append(
                {
                    "id": stable("check", source["id"] + "narrative-counts"),
                    "name": "Narrative cohort-count reconciliation",
                    "status": "passed" if matches else "flagged",
                    "detail": f"Declared total {total}; training + test {train + test}",
                    "evidence": [source],
                }
            )
            if not matches:
                findings.append(
                    finding(
                        "Narrative cohort counts require reconciliation",
                        "sample_count",
                        "supported_concern",
                        "medium",
                        "The paragraph's explicit total differs from its explicit training plus test counts.",
                        [source],
                        {"total": total, "training": train, "test": test},
                        alternatives=[
                            "Validation/excluded observations, overlapping cohorts or distinct populations may explain the difference"
                        ],
                        limitations=[
                            "The paragraph's partition convention must be established before calling the difference an error"
                        ],
                    )
                )
    return findings, checks, questions, handled
