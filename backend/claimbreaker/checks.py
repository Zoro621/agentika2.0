"""Deterministic evidence checks. No model response can set a verified status."""

import hashlib
import re
from decimal import Decimal

METRICS = r"accuracy|auroc|roc[_ -]?auc|auc|f1(?:[_ -]?score)?|precision|recall|rmse|mae|r2"
CONTEXT_KEYS = (
    "dataset",
    "model",
    "split",
    "averaging",
    "version",
    "run",
    "seed",
    "aggregation",
    "population",
    "subset",
)
METRIC_RE = re.compile(
    rf"\b(?P<metric>{METRICS})\b\s*(?:\([^)]{{0,70}}\))?\s*(?:(?:of|was|is|reached|achieved|equals|at)\s*|[:=]\s*)?(?P<value>-?(?:\d+(?:\.\d+)?|\.\d+))\s*(?P<pct>%|percent)?",
    re.I,
)


def stable(prefix, text):
    return prefix + "-" + hashlib.sha256(text.encode()).hexdigest()[:14]


def metric_name(name):
    name = re.sub(r"[^a-z0-9]", "", name.lower())
    return {
        "rocauc": "auc",
        "auroc": "auc",
        "f1score": "f1",
        "f1macro": "f1",
        "f1micro": "f1",
        "f1weighted": "f1",
        "testaccuracy": "accuracy",
        "accuracytest": "accuracy",
    }.get(name, name)


def locate(artifact, quote):
    normalized = " ".join(quote.split())
    for a in artifact["parsed"].get("anchors", []):
        if normalized in " ".join(a["text"].split()):
            return {**a, "text": quote, "context_excerpt": a["text"]}
    # Quotes spanning an extraction chunk retain the artifact, but not a fabricated line/page.
    return {
        "id": artifact["id"] + ":document",
        "artifact_id": artifact["id"],
        "path": artifact["path"],
        "text": quote,
        "kind": "document",
    }


def at_line(artifact, line):
    cell_call = next(
        (
            c
            for c in artifact["parsed"].get("code", {}).get("calls", [])
            if c["line"] == line and "cell" in c
        ),
        None,
    )
    if cell_call:
        source = next(
            (
                a
                for a in artifact["parsed"].get("anchors", [])
                if a.get("cell") == cell_call["cell"] and a.get("kind") != "saved_output"
            ),
            None,
        )
        if source:
            return {**source, "highlight_line": cell_call["cell_line"]}
    for source in artifact["parsed"].get("anchors", []):
        start = source.get("line")
        if start is not None and start <= line < start + len(source["text"].splitlines()):
            return {**source, "highlight_line": line}
    return None


def context_from_text(text):
    context = {}
    for key in CONTEXT_KEYS:
        m = re.search(rf"\b{key}\s*[:=]\s*([\w./-]+)", text, re.I)
        if m:
            context[key] = m.group(1)
    return context


def extract_claims(artifacts):
    claims = []
    for artifact in artifacts:
        if artifact["kind"] not in {"paper", "documentation"}:
            continue
        text = artifact["parsed"].get("text", "")
        for match in METRIC_RE.finditer(text):
            sentence = text.rfind(". ", 0, match.start())
            start = max(
                text.rfind("\n", 0, match.start()) + 1, sentence + 2 if sentence >= 0 else 0
            )
            end = text.find("\n", match.end())
            if end == -1:
                end = min(len(text), match.end() + 180)
            quote = text[start:end].strip()
            raw = match.group("value")
            value = float(raw)
            percent = bool(match.group("pct"))
            if percent:
                value /= 100
            decimals = len(raw.split(".")[1]) if "." in raw else 0
            tolerance = 0.5 * (10**-decimals) / (100 if percent else 1)
            metric = metric_name(match.group("metric"))
            if metric in {"accuracy", "auc", "f1", "precision", "recall"} and not 0 <= value <= 1:
                continue
            ctx = context_from_text(quote)
            aggregation = re.search(
                r"\b(mean|median|best)\s+(?:(?:test|validation)\s+)?(?:accuracy|f1|auc|rmse|mae)\b",
                quote,
                re.I,
            )
            if aggregation:
                ctx.setdefault("aggregation", aggregation.group(1).lower())
            averaging = re.search(r"\b(macro|micro|weighted)(?:[- ]averaged)?\b", quote, re.I)
            if averaging:
                ctx.setdefault("averaging", averaging.group(1).lower())
            anchor = locate(artifact, quote)
            claims.append(
                {
                    "id": stable("claim", artifact["id"] + str(match.start())),
                    "artifact_id": artifact["id"],
                    "quote": quote,
                    "type": "numerical",
                    "metric": metric,
                    "value": value,
                    "reported": match.group(0),
                    "tolerance": tolerance,
                    "units": "fraction"
                    if metric in {"accuracy", "auc", "f1", "precision", "recall"}
                    else "reported scale",
                    "context": ctx,
                    "anchor": anchor,
                    "origin": "deterministic extraction",
                }
            )
    from .paper_checks import table_claims

    for artifact in artifacts:
        if artifact["kind"] == "paper":
            claims.extend(table_claims(artifact))
    return claims[:200]


def finding(
    title,
    kind,
    status,
    impact,
    explanation,
    evidence,
    observed=None,
    alternatives=None,
    limitations=None,
    next_action=None,
):
    return {
        "id": stable("finding", title + "|" + "|".join(x.get("id", "") for x in evidence)),
        "title": title,
        "kind": kind,
        "evidence_status": status,
        "impact": impact,
        "explanation": explanation,
        "evidence": evidence,
        "observed": observed or {},
        "alternatives": alternatives or [],
        "limitations": limitations or [],
        "next_action": next_action or "Review the linked evidence and confirm its interpretation.",
        "review_status": "unreviewed",
        "review_note": "",
        "superseded": False,
    }


def compatible(left, right):
    mismatches = []
    for key in CONTEXT_KEYS:
        if left.get(key) and right.get(key) and str(left[key]).lower() != str(right[key]).lower():
            mismatches.append(key)
    return mismatches


def compare_metrics(artifacts, claims, decisions):
    findings, checks = [], []
    version_answer = next(
        (d["answer"] for d in reversed(decisions) if d["question_id"] == "repository-version"), None
    )
    for claim in claims:
        if claim.get("value") is None or not claim.get("metric"):
            continue
        candidates = []
        for art in artifacts:
            if art["kind"] != "results" and not art["parsed"].get("saved_outputs"):
                continue
            for number in art["parsed"].get("numbers", []):
                if metric_name(number["key"]) != claim["metric"]:
                    continue
                value = number["value"]
                if str(number.get("context", {}).get("units", "")).lower() in {
                    "%",
                    "percent",
                    "percentage",
                }:
                    value /= 100
                if (
                    claim["metric"] in {"accuracy", "auc", "f1", "precision", "recall"}
                    and not 0 <= value <= 1
                ):
                    continue  # Never assume an unlabeled 0-100 scale.
                mismatches = compatible(claim.get("context", {}), number.get("context", {}))
                candidates.append((art, number, value, mismatches))
        if not candidates:
            checks.append(
                {
                    "id": stable("check", claim["id"] + "missing-metric"),
                    "name": "Metric evidence availability",
                    "status": "inconclusive",
                    "detail": f"No recognized saved-result record for {claim['metric']}. Missing evidence does not disprove the claim.",
                    "claim_id": claim["id"],
                }
            )
            continue
        candidates.sort(key=lambda x: len(x[3]))
        exact = [c for c in candidates if not c[3]]
        # Multiple results require trial-aware matching; don't cherry-pick a convenient number.
        if len(exact) > 1 and not claim.get("context", {}).get("run"):
            values = [c[2] for c in exact]
            checks.append(
                {
                    "id": stable("check", claim["id"] + "ambiguous"),
                    "name": "Metric artifact matching",
                    "status": "inconclusive",
                    "detail": f"{len(exact)} possible result records; trial/aggregation needs clarification",
                    "claim_id": claim["id"],
                }
            )
            continue
        art, number, value, mismatches = candidates[0]
        source = {
            "id": art["id"] + number["pointer"],
            "artifact_id": art["id"],
            "path": art["path"],
            "pointer": number["pointer"],
            "line": number.get("line"),
            "kind": "derived_metric" if number.get("derived") else "result",
            "text": f"{number['pointer']}: {value}\n"
            + (
                f"Recomputed from {number['rows']} supplied y_true/y_pred rows.\n"
                if number.get("derived")
                else ""
            )
            + f"Context: {number.get('context', {})}",
        }
        if number.get("saved_output"):
            source.update(kind="saved_output", cell=number["cell"], text=number["quote"])
        matched = abs(claim["value"] - value) <= claim.get("tolerance", 0.0005) + 1e-10
        if mismatches:
            checks.append(
                {
                    "id": stable("check", claim["id"] + art["id"]),
                    "name": "Metric comparability",
                    "status": "inconclusive",
                    "detail": "Different "
                    + ", ".join(mismatches)
                    + "; values not directly comparable",
                    "claim_id": claim["id"],
                }
            )
            continue
        status = "passed" if matched else "flagged"
        checks.append(
            {
                "id": stable("check", claim["id"] + art["id"]),
                "name": "Claim ↔ saved result",
                "status": status,
                "detail": f"Reported {claim['value']:.6g}; artifact {value:.6g}",
                "claim_id": claim["id"],
                "artifact_id": art["id"],
                "evidence": [claim["anchor"], source],
            }
        )
        if matched:
            continue
        verified = (
            version_answer == "same"
            and len(exact) == 1
            and bool(claim.get("context", {}).get("dataset"))
            and bool(number.get("context", {}).get("dataset"))
        )
        noncorresponding = version_answer in {"different", "unknown"}
        if noncorresponding:
            checks[-1]["status"] = "inconclusive"
            checks[-1]["detail"] += "; publication/source correspondence was not established"
        findings.append(
            finding(
                f"{claim['metric'].upper()}: paper and saved result differ",
                "paper_repository",
                "inconclusive"
                if noncorresponding
                else "verified_artifact_discrepancy"
                if verified
                else "supported_concern",
                "informational" if noncorresponding else "high",
                "The human decision identifies different or unconfirmed source correspondence. These values cannot establish a paper-to-repository discrepancy; they are retained for traceability."
                if noncorresponding
                else "The quoted claim and supplied result artifact report different values. This compares saved evidence; it is not an independent reproduction.",
                [claim["anchor"], source],
                {
                    "metric": claim["metric"],
                    "reported": claim["value"],
                    "artifact": value,
                    "delta": value - claim["value"],
                    "tolerance": claim.get("tolerance"),
                },
                [
                    "A different publication/repository version",
                    "A different seed, trial, aggregation, or data subset",
                ],
                []
                if verified
                else [
                    "Publication-to-repository correspondence and full experiment context require human verification"
                ],
                "Confirm that the source snapshot and result correspond to the paper's experiment.",
            )
        )
    return findings, checks


def paper_internal(claims):
    findings, checks = [], []
    for i, left in enumerate(claims):
        for right in claims[i + 1 :]:
            if (
                left["artifact_id"] != right["artifact_id"]
                or left.get("metric") != right.get("metric")
                or left.get("value") is None
                or right.get("value") is None
            ):
                continue
            if compatible(left.get("context", {}), right.get("context", {})):
                continue
            if (
                abs(left["value"] - right["value"])
                <= left.get("tolerance", 0) + right.get("tolerance", 0) + 1e-10
            ):
                continue
            explicit = all(
                left.get("context", {}).get(k)
                and left["context"][k] == right.get("context", {}).get(k)
                for k in ("dataset", "split", "model")
            )
            if not explicit:
                continue
            findings.append(
                finding(
                    f"Conflicting {left['metric'].upper()} values in the same document",
                    "paper_internal",
                    "supported_concern",
                    "high",
                    "Two passages explicitly identify the same model, dataset, and split, but report different numerical values.",
                    [left["anchor"], right["anchor"]],
                    {
                        "reported": left["value"],
                        "artifact": right["value"],
                        "metric": left["metric"],
                    },
                    ["Different trials or aggregation may not be stated in these passages"],
                    ["Human review of the surrounding paper context is required"],
                )
            )
    return findings, checks


def methodology(artifacts, decisions):
    findings, checks, questions = [], [], []
    answers = {d["question_id"]: d["answer"] for d in decisions}
    data = [a for a in artifacts if a["kind"] == "data" and a["parsed"].get("profile")]
    codes = [a for a in artifacts if a["parsed"].get("code")]
    for a in codes:
        profile = a["parsed"]["code"]
        evidence = a["parsed"].get("anchors", [])[:1]
        if not profile.get("supported", True):
            checks.append(
                {
                    "id": stable("check", a["id"] + "unsupported"),
                    "name": "Execution support",
                    "status": "skipped",
                    "detail": profile.get("reason", "Unsupported execution profile"),
                }
            )
        if profile.get("preprocessing_before_split"):
            fit = next(
                (call for call in profile.get("calls", []) if call["name"] == "fit_transform"), None
            )
            anchored = at_line(a, fit["line"]) if fit else None
            evidence = [anchored] if anchored else evidence
            findings.append(
                finding(
                    "Preprocessing appears to be fitted before the split",
                    "methodology",
                    "candidate",
                    "medium",
                    "A fit_transform call precedes train_test_split in source order. Data-flow and transformer semantics need review before calling this leakage.",
                    evidence,
                    alternatives=["The operation may fit unrelated data or a fixed transformation"],
                    limitations=["Source order alone does not prove data flow"],
                    next_action="Inspect which data is used to fit the transformer.",
                )
            )
    if any(a["parsed"]["code"].get("split") == "random" for a in codes):
        for a in data:
            p = a["parsed"]["profile"]
            repeated = {k: v for k, v in p.get("repeated_entities", {}).items() if v > 0}
            if repeated:
                qid = "generalization"
                questions.append(
                    {
                        "id": qid,
                        "title": "What should this model generalize to?",
                        "why": "Repeated entities appear in the dataset, while the code uses a random row split. The right evaluation depends on the intended use.",
                        "evidence": a["parsed"].get("anchors", [])[:1],
                        "options": [
                            {
                                "value": "new_entities",
                                "label": "New individuals",
                                "effect": "Keep each entity entirely within one partition and rerun grouped evaluation.",
                            },
                            {
                                "value": "known_entities",
                                "label": "New observations of known individuals",
                                "effect": "Keep the row-level interpretation, with its dependence assumptions visible.",
                            },
                            {
                                "value": "unknown",
                                "label": "I don't know yet",
                                "effect": "Leave the generalization claim unresolved; continue independent checks.",
                            },
                        ],
                        "answer": answers.get(qid),
                    }
                )
                if answers.get(qid) != "known_entities":
                    findings.append(
                        finding(
                            "Repeated individuals may cross the evaluation boundary",
                            "methodology",
                            "supported_concern"
                            if answers.get(qid) == "new_entities"
                            else "candidate",
                            "high",
                            f"Repeated observations were found for {', '.join(repeated)}. A random row split may mix the same individual across training and test partitions.",
                            a["parsed"].get("anchors", [])[:1],
                            {"repeated_rows": repeated},
                            [
                                "Row-level evaluation may be appropriate when predicting observations for known individuals"
                            ],
                            ["Entity semantics and intended deployment require human judgment"],
                            "Confirm the intended population, then inspect a grouped re-evaluation.",
                        )
                    )
    for a in data:
        columns = [c["name"] for c in a["parsed"]["profile"].get("columns", [])]
        suspicious = [
            c
            for c in columns
            if re.search(
                r"post[_-]|after[_-]|outcome[_-](?:code|date)|discharge|future[_-]", c, re.I
            )
        ]
        for column in suspicious[:3]:
            qid = "availability:" + column
            questions.append(
                {
                    "id": qid,
                    "title": f"Was “{column}” available at prediction time?",
                    "why": "The name suggests it may be recorded after the outcome. A name is a clue, not proof.",
                    "evidence": a["parsed"].get("anchors", [])[:1],
                    "options": [
                        {
                            "value": "before",
                            "label": "Available before prediction",
                            "effect": "Dismiss this timing concern.",
                        },
                        {
                            "value": "after",
                            "label": "Only available afterward",
                            "effect": "Exclude it from a corrected re-evaluation; retain the original baseline.",
                        },
                        {
                            "value": "unknown",
                            "label": "Uncertain",
                            "effect": "Keep the feature-timing issue unresolved.",
                        },
                    ],
                    "answer": answers.get(qid),
                }
            )
            if answers.get(qid) != "before":
                findings.append(
                    finding(
                        f"Timing of “{column}” needs clarification",
                        "feature_timing",
                        "supported_concern" if answers.get(qid) == "after" else "candidate",
                        "high",
                        "A potentially post-outcome feature may be included. The researcher must establish when it is measured and whether the model uses it.",
                        a["parsed"].get("anchors", [])[:1],
                        limitations=["Column names do not establish temporal availability"],
                        next_action="Answer the feature-availability question.",
                    )
                )
    return findings, checks, questions


def graph_for(artifacts, claims, findings, executions, questions, checks=None):
    nodes, edges = [], []
    for a in artifacts:
        nodes.append(
            {
                "id": a["id"],
                "label": a["path"].split("/")[-1],
                "type": a["kind"],
                "artifact_id": a["id"],
                "path": a["path"],
            }
        )
    for c in claims:
        nodes.append(
            {
                "id": c["id"],
                "label": c.get("reported", c["quote"][:45]),
                "type": "claim",
                "claim_id": c["id"],
            }
        )
        edges.append({"source": c["artifact_id"], "target": c["id"], "type": "derived_from"})
    for f in findings:
        nodes.append(
            {
                "id": f["id"],
                "label": f["title"],
                "type": "finding",
                "finding_id": f["id"],
                "status": f["evidence_status"],
            }
        )
        for a in f["evidence"]:
            if a.get("artifact_id"):
                edges.append(
                    {
                        "source": a["artifact_id"],
                        "target": f["id"],
                        "type": "conflicts_with"
                        if f["kind"] in {"paper_repository", "paper_internal"}
                        else "requires_clarification",
                    }
                )
            if a.get("execution_id"):
                edges.append(
                    {"source": a["execution_id"], "target": f["id"], "type": "derived_from"}
                )
    for e in executions:
        nodes.append(
            {
                "id": e["id"],
                "label": e.get("manifest", {}).get("variant", "Evaluation"),
                "type": "execution",
                "status": e["status"],
            }
        )
        if e.get("manifest", {}).get("dataset_id"):
            edges.append(
                {"source": e["manifest"]["dataset_id"], "target": e["id"], "type": "derived_from"}
            )
    for q in questions:
        nodes.append(
            {
                "id": q["id"],
                "label": q["title"],
                "type": "decision",
                "status": "answered" if q.get("answer") else "pending",
            }
        )
        for a in q.get("evidence", []):
            origin = a.get("artifact_id") or a.get("execution_id")
            if origin:
                edges.append(
                    {"source": origin, "target": q["id"], "type": "requires_clarification"}
                )
    for check in checks or []:
        if (
            check.get("claim_id")
            and (check.get("artifact_id") or check.get("execution_id"))
            and check["status"] in {"passed", "flagged"}
        ):
            edges.append(
                {
                    "source": check.get("artifact_id") or check["execution_id"],
                    "target": check["claim_id"],
                    "type": "supports" if check["status"] == "passed" else "conflicts_with",
                }
            )
    known = {n["id"] for n in nodes}
    return {
        "nodes": nodes,
        "edges": [e for e in edges if e["source"] in known and e["target"] in known],
    }
