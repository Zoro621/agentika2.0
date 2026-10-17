"""Scientific prerequisites and versioned researcher mappings for bounded execution."""

from pathlib import Path
from .checks import stable
from .original_worker import supported_source


def original_eligible(artifact, inventory):
    profile = artifact["parsed"].get("code", {})
    if not profile.get("estimator") or profile.get("reason", "").startswith(
        ("Deep-learning", "Multiple estimator")
    ):
        return False
    modules = {
        Path(a["path"]).parts[0].removesuffix(".py") for a in inventory if a["path"].endswith(".py")
    }
    text = artifact["parsed"].get("code_source", artifact["parsed"].get("text", ""))
    if not text.strip():
        return False
    try:
        supported_source(text, modules)
    except (ValueError, SyntaxError):
        return False
    return True


def candidates(inventory):
    return [
        a
        for a in inventory
        if a["parsed"].get("code", {}).get("estimator")
        and (a["parsed"]["code"].get("supported") or original_eligible(a, inventory))
    ]


def mapping(inventory, answers):
    sources = candidates(inventory)
    if len(sources) > 1:
        sources = [a for a in sources if a["id"] == answers.get("experiment-entry")]
    if len(sources) != 1:
        return None, None
    source = sources[0]
    datasets = [a for a in inventory if a["kind"] == "data" and a["parsed"].get("profile")]
    matches = [
        a
        for a in datasets
        if any(
            Path(a["path"]).name == Path(p).name
            for p in source["parsed"]["code"].get("datasets", [])
        )
    ]
    if len(matches) == 1:
        return source, matches[0]
    if len(datasets) == 1:
        return source, datasets[0]
    return source, next((a for a in datasets if a["id"] == answers.get("experiment-dataset")), None)


def question(id, title, why, evidence, options, answers):
    return {
        "id": id,
        "title": title,
        "why": why,
        "evidence": evidence,
        "options": [
            {"value": value, "label": label, "effect": effect} for value, label, effect in options
        ]
        + [
            {
                "value": "unknown",
                "label": "I don't know yet",
                "effect": "Leave this mapping unresolved; continue independent checks.",
            }
        ],
        "answer": answers.get(id),
    }


def execution_questions(inventory, decisions, primary_paper=None):
    answers = {d["question_id"]: d["answer"] for d in decisions}
    if primary_paper:
        answers.setdefault("primary-paper", primary_paper)
    sources = candidates(inventory)
    questions = []
    if len(sources) > 1:
        questions.append(
            question(
                "experiment-entry",
                "Which experiment should this investigation re-evaluate?",
                "Several CPU entry points were discovered. The experiment is a scientific choice.",
                [e for a in sources[:3] for e in a["parsed"].get("anchors", [])[:1]],
                [
                    (
                        a["id"],
                        a["path"],
                        "Use this immutable entry point and preserve its original scientific operations.",
                    )
                    for a in sources[:30]
                ],
                answers,
            )
        )
    source, data = mapping(inventory, answers)
    datasets = [a for a in inventory if a["kind"] == "data" and a["parsed"].get("profile")]
    if source and not data and len(datasets) > 1:
        questions.append(
            question(
                "experiment-dataset",
                "Which dataset corresponds to this experiment?",
                "The referenced data path cannot be resolved uniquely.",
                source["parsed"].get("anchors", [])[:1],
                [
                    (a["id"], a["path"], "Use this dataset's immutable bytes.")
                    for a in datasets[:30]
                ],
                answers,
            )
        )
    if source and data:
        profile = source["parsed"]["code"]
        columns = [c["name"] for c in data["parsed"]["profile"]["columns"]]
        target = profile.get("target") or answers.get("target:" + source["id"])
        if target not in columns:
            questions.append(
                question(
                    "target:" + source["id"],
                    "Which column is the prediction target?",
                    "No target was established by the supported static mapping. This answer affects corrected evaluation; the original program is not rewritten.",
                    data["parsed"].get("anchors", [])[:1],
                    [
                        (
                            c,
                            c,
                            "Use this supplied column as the target in an explicitly labeled reconstructed/corrected evaluation.",
                        )
                        for c in columns[:200]
                    ],
                    answers,
                )
            )
        if profile.get("features") is None and profile.get("feature_exclusions") is None:
            questions.append(
                question(
                    "features:" + source["id"],
                    "Which feature boundary should a corrected evaluation use?",
                    "The source feature transformation cannot be mapped exactly. Original execution, when eligible, retains its own code. A corrected reconstruction requires an explicit column policy.",
                    source["parsed"].get("anchors", [])[:1],
                    [
                        (
                            "all_except_target",
                            "All columns except the target",
                            "Use all supplied columns except the chosen target; inspect the column list before answering.",
                        ),
                        (
                            "non_identifiers",
                            "Exclude target and entity identifiers",
                            "Use supplied columns except the target and discovered entity identifier columns.",
                        ),
                    ],
                    answers,
                )
            )
    papers = [a for a in inventory if a["kind"] == "paper"]
    if len(papers) > 1:
        questions.append(
            question(
                "primary-paper",
                "Which paper corresponds to the repository experiment?",
                "Multiple papers are present. Internal checks can continue, but repository correspondence must be established.",
                [e for a in papers[:3] for e in a["parsed"].get("anchors", [])[:1]],
                [
                    (
                        a["id"],
                        a["path"],
                        "Use this paper for repository comparisons; retain the other documents as inspectable sources.",
                    )
                    for a in papers[:30]
                ],
                answers,
            )
        )
    return questions


def execution_plan(inventory, decisions):
    answers = {d["question_id"]: d["answer"] for d in decisions}
    source, data = mapping(inventory, answers)
    if not source or not data:
        return (
            [],
            "A unique CPU entry point and dataset must be established; inspect the scientific mapping questions",
        )
    p = source["parsed"]["code"]
    profile = data["parsed"]["profile"]
    columns = [c["name"] for c in profile["columns"]]
    target = p.get("target") or answers.get("target:" + source["id"])
    if target not in columns:
        return [], "Target column remains unresolved; no scientific assumption was guessed"
    features = p.get("features")
    if features is None and p.get("feature_exclusions") is not None:
        features = [c for c in columns if c not in p["feature_exclusions"]]
    policy = answers.get("features:" + source["id"])
    if features is None and policy in {"all_except_target", "non_identifiers"}:
        features = [
            c
            for c in columns
            if c != target
            and (policy != "non_identifiers" or c not in profile.get("entity_columns", []))
        ]
    original = original_eligible(source, inventory)
    if not features and not original:
        return [], "Feature mapping remains unresolved"
    if not original and (
        target in (features or []) or any(c not in columns for c in (features or []))
    ):
        return [], "Feature mapping includes an unavailable column or the target"
    if profile.get("sampled"):
        return [], "Dataset exceeds the supported 50,000-row execution boundary"
    entity = profile.get("entity_columns", [])
    entity = entity[0] if len(entity) == 1 else None
    base = {
        "dataset_id": data["id"],
        "code_id": source["id"],
        "target": target,
        "features": features or [],
        "estimator": p["estimator"],
        "params": p.get("params", {}),
        "seed": p.get("seed") if p.get("seed") is not None else 42,
        "seed_origin": "source"
        if p.get("seed") is not None
        else "fixed reconstruction seed; original execution preserves source randomness",
        "test_size": p.get("test_size", 0.25),
        "entity": entity,
        "scaling": p.get("scaling", False),
        "stratify": p.get("stratify", False),
        "imputer_strategy": p.get("imputer_strategy", "median"),
        "exclude": [],
        "variant": "baseline",
        "cv": p.get("cv"),
        "execution_mode": "original" if original else "reconstruction",
        "entry_path": source["path"],
        "preprocessing_policy": "as_source" if original else "training_only",
    }
    if not original and p.get("split") not in {"random", "cv"}:
        return [], "Evaluation protocol is outside the reconstructable support profile"
    plans = [base]
    reconstruction = bool(
        features
        and p.get("supported")
        and target not in features
        and all(c in columns for c in features)
    )
    numeric_types = ("int", "float", "uint", "bool")
    if any(
        c["name"] in (features or []) and not c["dtype"].startswith(numeric_types)
        for c in profile["columns"]
    ) and not any(v in p.get("preprocessors", []) for v in ("OneHotEncoder", "get_dummies")):
        reconstruction = False
    if not reconstruction:
        return (
            plans,
            "Original source can execute; a corrected reconstruction still needs an established feature/transformation policy",
        )
    preprocessing_choice = answers.get(stable("preprocessing", source["id"]))
    if p.get("preprocessing_dataflow") and preprocessing_choice != "training_only":
        return (
            plans,
            "Original baseline retained. Corrected reconstruction requires an explicit training-only preprocessing decision; its learned transforms must not be silently changed.",
        )
    future = next(
        (
            t["column"]
            for t in profile.get("time_columns", [])
            if answers.get(stable("temporal", data["id"] + t["column"])) == "future"
        ),
        None,
    )
    grouped = answers.get("generalization") == "new_entities" and entity
    mode = (
        "grouped_temporal"
        if grouped and future
        else "temporal"
        if future
        else "grouped"
        if grouped
        else "random"
    )
    correction = {
        **base,
        "execution_mode": "reconstruction",
        "split_mode": mode,
        "time_column": future,
        "preprocessing_policy": "training_only",
    }
    if grouped or future:
        plans.append({**correction, "variant": "temporal" if future else "grouped"})
    exclude = [
        qid.split(":", 1)[1]
        for qid, value in answers.items()
        if qid.startswith("availability:") and value == "after"
    ]
    if exclude:
        plans.append({**correction, "exclude": exclude, "variant": "corrected_features"})
    if preprocessing_choice == "training_only" and len(plans) == 1:
        plans.append({**correction, "exclude": exclude, "variant": "corrected_preprocessing"})
    return plans[:3], None
