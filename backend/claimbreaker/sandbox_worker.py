"""Trusted numeric runner. Never imports or evaluates uploaded project code."""

import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path


def evaluate(payload):
    os.environ.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    import numpy as np
    import pandas as pd
    import sklearn
    from sklearn.model_selection import train_test_split, GroupShuffleSplit
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.linear_model import LogisticRegression, LinearRegression, Ridge
    from sklearn.metrics import (
        accuracy_score,
        f1_score,
        mean_squared_error,
        r2_score,
        confusion_matrix,
    )
    from sklearn.preprocessing import StandardScaler, OneHotEncoder
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer

    started = time.monotonic()
    spec = payload["spec"]
    frame = pd.read_csv(io.StringIO(payload["csv"]), nrows=50001)
    if len(frame) > 50000 or len(frame.columns) > 200:
        raise ValueError("Execution support limit: 50,000 rows / 200 columns")
    target = spec["target"]
    if target not in frame:
        raise ValueError("Target is absent from data")
    features = spec.get("features") or [
        c for c in frame.columns if c not in {target, *spec.get("exclude", [])}
    ]
    features = [c for c in features if c != target and c not in spec.get("exclude", [])]
    if not features or any(c not in frame for c in features):
        raise ValueError("Unsupported feature mapping")
    if frame[target].isna().any():
        raise ValueError("Missing target labels require a researcher-approved handling policy")
    X, y = frame[features], frame[target]
    seed = spec.get("seed") if isinstance(spec.get("seed"), int) else 42
    fraction = spec.get("test_size", 0.25)
    if not isinstance(fraction, (float, int)) or not 0.05 <= fraction <= 0.5:
        raise ValueError("Unsupported test fraction")
    variant = spec["variant"]
    indices = np.arange(len(frame))
    cv = spec.get("cv")
    if cv:
        train_idx, test_idx = indices, indices
    elif variant == "grouped" or spec.get("split_mode") == "grouped":
        entity = spec.get("entity")
        if entity not in frame or frame[entity].isna().any():
            raise ValueError("Grouping requires complete entity identifiers")
        if frame[entity].nunique() < 4:
            raise ValueError("Not enough independent groups")
        train_idx, test_idx = next(
            GroupShuffleSplit(n_splits=1, test_size=fraction, random_state=seed).split(
                X, y, groups=frame[entity]
            )
        )
    elif variant == "temporal" or spec.get("split_mode") in {"temporal", "grouped_temporal"}:
        time_col = spec.get("time_column")
        if time_col not in frame:
            raise ValueError("A temporal ordering column must be confirmed")
        times = pd.to_datetime(
            frame[time_col].astype(str), errors="coerce", format="mixed", utc=True
        )
        if times.isna().any():
            raise ValueError(
                "Temporal evaluation requires a complete interpretable ordering column"
            )
        ordered = times.sort_values(kind="stable").index.to_numpy()
        cut = int(len(ordered) * (1 - fraction))
        train_idx, test_idx = ordered[:cut], ordered[cut:]
        if spec.get("split_mode") == "grouped_temporal":
            if spec.get("entity") not in frame:
                raise ValueError(
                    "Combined group/time evaluation requires confirmed entity identifiers"
                )
            test_entities = set(frame.iloc[test_idx][spec["entity"]])
            train_idx = np.array(
                [i for i in train_idx if frame.iloc[i][spec["entity"]] not in test_entities]
            )
            if len(train_idx) < 5:
                raise ValueError(
                    "Insufficient past observations of disjoint entities for the confirmed protocol"
                )
    else:
        train_idx, test_idx = train_test_split(
            indices,
            test_size=fraction,
            random_state=seed,
            stratify=y if spec.get("stratify") else None,
        )
    estimators = {
        "RandomForestClassifier": RandomForestClassifier,
        "DecisionTreeClassifier": DecisionTreeClassifier,
        "LogisticRegression": LogisticRegression,
        "LinearRegression": LinearRegression,
        "Ridge": Ridge,
        "RandomForestRegressor": RandomForestRegressor,
    }
    model_name = spec["estimator"]
    if model_name not in estimators:
        raise ValueError("Estimator is outside the supported profile")
    regression = model_name in {"LinearRegression", "Ridge", "RandomForestRegressor"}
    if not regression and y.nunique() > 50:
        raise ValueError("Too many target classes for this support profile")
    allowed = {
        "n_estimators",
        "max_depth",
        "min_samples_split",
        "min_samples_leaf",
        "C",
        "max_iter",
        "alpha",
        "criterion",
        "solver",
        "penalty",
        "max_features",
        "class_weight",
        "bootstrap",
        "fit_intercept",
        "random_state",
    }
    unsupported = set(spec.get("params", {})) - allowed - {"n_jobs"}
    if unsupported:
        raise ValueError("Unsupported estimator settings: " + ", ".join(sorted(unsupported)))
    if any(
        k in allowed and not isinstance(v, (int, float, str, bool, type(None)))
        for k, v in spec.get("params", {}).items()
    ):
        raise ValueError("Structured estimator settings require explicit mapping")
    params = {
        k: v
        for k, v in spec.get("params", {}).items()
        if k in allowed and isinstance(v, (int, float, str, bool, type(None)))
    }
    if "n_estimators" in params and not 1 <= int(params["n_estimators"]) <= 200:
        raise ValueError(
            "Source tree count exceeds execution support; scientific parameters are not silently changed"
        )
    if "max_iter" in params and not 1 <= int(params["max_iter"]) <= 1000:
        raise ValueError("Source iteration count exceeds execution support")
    if model_name not in {"LinearRegression", "Ridge"}:
        params.setdefault("random_state", None)
    if model_name in {
        "RandomForestClassifier",
        "RandomForestRegressor",
        "LogisticRegression",
        "LinearRegression",
    }:
        params["n_jobs"] = 1
    numeric = list(X.select_dtypes(include="number").columns)
    categorical = [c for c in features if c not in numeric]
    if any(X[c].nunique() > 1000 for c in categorical):
        raise ValueError("High-cardinality categorical feature needs explicit preprocessing")
    strategy = spec.get("imputer_strategy", "median")
    if strategy not in {"mean", "median", "most_frequent"}:
        raise ValueError("Unsupported source imputation strategy")
    if categorical and X[categorical].isna().any().any() and strategy != "most_frequent":
        raise ValueError(
            "Categorical missing-value policy is not established by this source imputer"
        )
    numeric_steps = [("imputer", SimpleImputer(strategy=strategy))]
    if spec.get("scaling"):
        numeric_steps.append(("scaler", StandardScaler()))
    transform = ColumnTransformer(
        [
            ("numeric", Pipeline(numeric_steps), numeric),
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("encoder", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical,
            ),
        ]
    )
    model = Pipeline([("preprocess", transform), ("model", estimators[model_name](**params))])
    folds = []
    cv_overlap = None
    if cv:
        from sklearn.base import clone
        from sklearn.model_selection import KFold, StratifiedKFold, GroupKFold, TimeSeriesSplit
        from sklearn.metrics import get_scorer

        count = cv.get("folds", 5)
        if not isinstance(count, int) or not 2 <= count <= 10:
            raise ValueError("CV support is 2–10 folds")
        kind = cv.get("kind", "default")
        grouped = (
            spec.get("split_mode") in {"grouped", "grouped_temporal"}
            or variant == "grouped"
            or kind == "GroupKFold"
        )
        temporal = (
            spec.get("split_mode") in {"temporal", "grouped_temporal"} or kind == "TimeSeriesSplit"
        )
        shuffle = bool(cv.get("shuffle", False))
        if temporal:
            column = spec.get("time_column")
            if column:
                times = pd.to_datetime(
                    frame[column].astype(str), errors="coerce", format="mixed", utc=True
                )
                if times.isna().any():
                    raise ValueError("CV chronology has missing or unparseable values")
                order = times.sort_values(kind="stable").index.to_numpy()
            else:
                order = indices
            pairs = [
                (order[a], order[b])
                for a, b in TimeSeriesSplit(
                    n_splits=count,
                    gap=cv.get("gap", 0),
                    max_train_size=cv.get("max_train_size"),
                    test_size=cv.get("test_size"),
                ).split(X)
            ]
        elif grouped:
            entity = spec.get("entity")
            if entity not in frame or frame[entity].isna().any():
                raise ValueError("Group CV needs complete confirmed identifiers")
            pairs = list(
                GroupKFold(
                    n_splits=count,
                    shuffle=shuffle,
                    random_state=cv.get("seed") if shuffle else None,
                ).split(X, y, groups=frame[entity])
            )
        else:
            klass = KFold if regression or kind == "KFold" else StratifiedKFold
            pairs = list(
                klass(
                    n_splits=count,
                    shuffle=shuffle,
                    random_state=cv.get("seed") if shuffle else None,
                ).split(X, y)
            )
        values = {}
        overlaps = []
        for fold, (train_idx, test_idx) in enumerate(pairs, 1):
            if temporal and grouped:
                entity = spec.get("entity")
                if entity not in frame:
                    raise ValueError("Combined chronology/group CV requires an entity column")
                test_entities = set(frame.iloc[test_idx][entity])
                train_idx = np.array(
                    [i for i in train_idx if frame.iloc[i][entity] not in test_entities]
                )
            fitted = clone(model).fit(X.iloc[train_idx], y.iloc[train_idx])
            predictions = fitted.predict(X.iloc[test_idx])
            measured = (
                {
                    "rmse": float(np.sqrt(mean_squared_error(y.iloc[test_idx], predictions))),
                    "r2": float(r2_score(y.iloc[test_idx], predictions)),
                }
                if regression
                else {
                    "accuracy": float(accuracy_score(y.iloc[test_idx], predictions)),
                    "f1_macro": float(
                        f1_score(y.iloc[test_idx], predictions, average="macro", zero_division=0)
                    ),
                }
            )
            scoring = cv.get("scoring")
            if scoring:
                score = float(get_scorer(scoring)(fitted, X.iloc[test_idx], y.iloc[test_idx]))
                measured[
                    "rmse"
                    if scoring == "neg_root_mean_squared_error"
                    else "auc"
                    if scoring == "roc_auc"
                    else scoring
                ] = -score if scoring == "neg_root_mean_squared_error" else score
            if spec.get("entity") in frame:
                overlaps.append(
                    len(
                        set(frame.iloc[train_idx][spec["entity"]])
                        & set(frame.iloc[test_idx][spec["entity"]])
                    )
                )
            folds.append(
                {
                    "fold": fold,
                    "train_rows": len(train_idx),
                    "test_rows": len(test_idx),
                    "metrics": measured,
                }
            )
            for key, value in measured.items():
                values.setdefault(key, []).append(value)
        metrics = {key: float(np.mean(value)) for key, value in values.items()}
        cv_overlap = sum(overlaps) if overlaps else None
        matrix = None
    elif regression:
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        predictions = model.predict(X.iloc[test_idx])
        metrics = {
            "rmse": float(np.sqrt(mean_squared_error(y.iloc[test_idx], predictions))),
            "r2": float(r2_score(y.iloc[test_idx], predictions)),
        }
        matrix = None
    else:
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        predictions = model.predict(X.iloc[test_idx])
        metrics = {
            "accuracy": float(accuracy_score(y.iloc[test_idx], predictions)),
            "f1_macro": float(
                f1_score(y.iloc[test_idx], predictions, average="macro", zero_division=0)
            ),
        }
        matrix = confusion_matrix(y.iloc[test_idx], predictions).tolist()
    entity = spec.get("entity")
    overlap = (
        cv_overlap
        if cv
        else (
            int(len(set(frame.iloc[train_idx][entity]) & set(frame.iloc[test_idx][entity])))
            if entity and entity in frame
            else None
        )
    )
    return {
        "metrics": metrics,
        "folds": folds,
        "aggregation": "mean of held-out fold metrics" if cv else "single held-out split",
        "train_rows": len(train_idx),
        "test_rows": len(test_idx),
        "entity_overlap": overlap,
        "features": features,
        "confusion_matrix": matrix,
        "seconds": round(time.monotonic() - started, 3),
        "environment": {
            "python": sys.version.split()[0],
            "sklearn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "classification": "reconstruction" if variant == "baseline" else "corrected_protocol",
        "limitations": [
            "Trusted reconstruction from discovered settings; original repository code was not executed",
            "Preprocessing is fitted within the training pipeline",
            "This run alone is not a directly comparable reproduction of a published result",
        ],
        "dataset_sha256": hashlib.sha256(payload["csv"].encode()).hexdigest(),
        "worker_sha256": hashlib.sha256(
            Path(__file__).read_text(encoding="utf-8").encode()
        ).hexdigest(),
        "spec": spec,
    }


if __name__ == "__main__":
    try:
        if sys.platform != "win32":
            import signal
            import resource

            def wall_timeout(*_):
                raise TimeoutError("Experiment exceeded the 90-second wall limit")

            signal.signal(signal.SIGALRM, wall_timeout)
            signal.alarm(90)
            resource.setrlimit(resource.RLIMIT_CPU, (85, 90))
        payload = json.loads(sys.stdin.read(105 * 1024 * 1024))
        if payload["spec"].get("execution_mode") == "original":
            import runpy

            result = runpy.run_path(str(Path(__file__).with_name("original_worker.py")))[
                "evaluate_original"
            ](payload)
            result.update(
                dataset_sha256=hashlib.sha256(payload["csv"].encode()).hexdigest(),
                worker_sha256=hashlib.sha256(
                    Path(__file__).read_text(encoding="utf-8").encode()
                ).hexdigest(),
                spec={k: v for k, v in payload["spec"].items() if k != "source_files"},
            )
        else:
            result = evaluate(payload)
        print(json.dumps({"ok": True, "result": result}, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:2000]}))
        sys.exit(1)
