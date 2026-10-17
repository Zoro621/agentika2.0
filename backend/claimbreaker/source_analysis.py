"""Conservative same-scope data-flow and explicit CV discovery, without executing source."""

import ast


def name(node):
    return (
        node.id
        if isinstance(node, ast.Name)
        else node.attr
        if isinstance(node, ast.Attribute)
        else ""
    )


def extra_profile(tree, target):
    calls, definitions, derived, flow = [], {}, [], []
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Call):
            for left in statement.targets:
                if isinstance(left, ast.Name):
                    definitions[left.id] = statement.value
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            for left in statement.targets:
                if (
                    isinstance(left, ast.Subscript)
                    and isinstance(left.slice, ast.Constant)
                    and isinstance(left.slice.value, str)
                ):
                    dependencies = sorted(
                        {
                            n.slice.value
                            for n in ast.walk(statement.value)
                            if isinstance(n, ast.Subscript)
                            and isinstance(n.slice, ast.Constant)
                            and isinstance(n.slice.value, str)
                        }
                    )
                    if target and target in dependencies:
                        derived.append(
                            {
                                "column": left.slice.value,
                                "line": statement.lineno,
                                "depends_on": target,
                            }
                        )
        for node in ast.walk(statement):
            if isinstance(node, ast.Call):
                calls.append(node)
    cv = None
    for call in calls:
        if name(call.func) not in {"cross_val_score", "cross_validate"}:
            continue
        if len(call.args) < 2 or name(call.args[1]) not in {"X", "features"}:
            continue
        options = {k.arg: k.value for k in call.keywords}
        node = options.get("cv", ast.Constant(value=5))
        if isinstance(node, ast.Name):
            node = definitions.get(node.id, node)
        config = {"folds": 5, "kind": "default", "shuffle": False, "seed": None, "scoring": None}
        try:
            if isinstance(node, ast.Constant) and isinstance(node.value, int):
                config["folds"] = node.value
            elif isinstance(node, ast.Call) and name(node.func) in {
                "KFold",
                "StratifiedKFold",
                "GroupKFold",
                "TimeSeriesSplit",
            }:
                values = {k.arg: ast.literal_eval(k.value) for k in node.keywords}
                config.update(
                    folds=values.get(
                        "n_splits", ast.literal_eval(node.args[0]) if node.args else 5
                    ),
                    kind=name(node.func),
                    shuffle=values.get("shuffle", False),
                    seed=values.get("random_state"),
                )
                if name(node.func) == "TimeSeriesSplit":
                    config.update(
                        {
                            key: values[key]
                            for key in ("gap", "test_size", "max_train_size")
                            if key in values
                        }
                    )
            else:
                continue
            if "scoring" in options:
                config["scoring"] = ast.literal_eval(options["scoring"])
            if config["scoring"] not in {
                None,
                "accuracy",
                "f1_macro",
                "r2",
                "neg_root_mean_squared_error",
                "roc_auc",
            }:
                continue
            if 2 <= config["folds"] <= 10:
                cv = config
        except (ValueError, TypeError):
            continue
    # Only a top-level X -> fitted-transform X -> split(X, ...) chain establishes this relation.
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or not isinstance(statement.value, ast.Call):
            continue
        fitted = statement.value
        if (
            name(fitted.func) != "fit_transform"
            or not fitted.args
            or not isinstance(fitted.func, ast.Attribute)
        ):
            continue
        variable = name(fitted.args[0])
        receiver = name(fitted.func.value)
        transform = name(definitions[receiver].func) if receiver in definitions else ""
        if (
            variable
            and any(name(x) == variable for x in statement.targets)
            and transform in {"StandardScaler", "MinMaxScaler", "PCA", "SimpleImputer"}
        ):
            splits = [
                c
                for c in calls
                if name(c.func) == "train_test_split"
                and c.args
                and name(c.args[0]) == variable
                and c.lineno > statement.lineno
            ]
            for split in splits:
                reset = any(
                    isinstance(s, ast.Assign)
                    and statement.lineno < s.lineno < split.lineno
                    and any(name(t) == variable for t in s.targets)
                    for s in tree.body
                )
                if not reset:
                    flow.append(
                        {
                            "fit_line": statement.lineno,
                            "split_line": split.lineno,
                            "variable": variable,
                            "transformer": transform,
                        }
                    )
    return {"cv": cv, "target_derived_features": derived, "preprocessing_dataflow": flow}
