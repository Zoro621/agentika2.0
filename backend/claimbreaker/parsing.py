import ast
import hashlib
import csv
import io
import json
import re
import tomllib
from pathlib import PurePosixPath
import numpy as np
import pandas as pd
import yaml
from .config import settings


def anchor(artifact, text, line=None, page=None, cell=None, pointer=None, kind="passage"):
    label = f"p{page}" if page else f"cell{cell}" if cell is not None else f"L{line or 1}"
    return {
        "id": f"{artifact.id}:{label}:{hashlib.sha256(text.encode()).hexdigest()[:10]}:{pointer or ''}",
        "artifact_id": artifact.id,
        "path": artifact.path,
        "text": text[:5000],
        "line": line,
        "page": page,
        "cell": cell,
        "pointer": pointer,
        "kind": kind,
    }


def parse(artifact, data):
    ext = PurePosixPath(artifact.path).suffix.lower()
    if ext == ".pdf":
        return parse_pdf(artifact, data)
    text = data.decode("utf-8-sig", errors="replace")
    if text.startswith("version https://git-lfs.github.com/spec/"):
        return {
            "text": text,
            "anchors": [],
            "warnings": ["Git LFS pointer: original data is not present"],
            "unavailable": True,
        }
    if ext in {".csv", ".tsv"}:
        return parse_csv(artifact, text, ext)
    if ext == ".ipynb":
        notebook = json.loads(text)
        chunks, anchors, source = [], [], []
        numbers, cell_ranges = [], []
        offset = 1
        from .checks import METRIC_RE, metric_name, context_from_text

        for idx, cell in enumerate(notebook.get("cells", [])[:500]):
            body = (
                "".join(cell.get("source", []))
                if isinstance(cell.get("source"), list)
                else str(cell.get("source", ""))
            )
            chunks.append(body)
            anchors.append(anchor(artifact, body, cell=idx))
            if cell.get("cell_type") == "code":
                source.append(body)
                cell_ranges.append((offset, offset + body.count("\n") + 1, idx))
                offset += body.count("\n") + 1
            for output_index, output in enumerate(cell.get("outputs", [])):
                content = output.get("text", output.get("data", {}).get("text/plain", ""))
                if isinstance(content, list):
                    content = "".join(content)
                if content:
                    anchors.append(anchor(artifact, str(content), cell=idx, kind="saved_output"))
                    for match in METRIC_RE.finditer(str(content)):
                        numbers.append(
                            {
                                "key": metric_name(match.group("metric")),
                                "value": float(match.group("value"))
                                / (100 if match.group("pct") else 1),
                                "pointer": f"cell/{idx}/output/{output_index}",
                                "cell": idx,
                                "context": context_from_text(str(content)),
                                "saved_output": True,
                                "quote": str(content)[:2000],
                            }
                        )
        profile = code_profile("\n".join(source))
        for call in profile.get("calls", []):
            for start, end, idx in cell_ranges:
                if start <= call["line"] < end:
                    call.update(cell=idx, cell_line=call["line"] - start + 1)
                    break
        return {
            "text": "\n\n".join(chunks),
            "code_source": "\n".join(source),
            "anchors": anchors,
            "code": profile,
            "numbers": numbers,
            "saved_outputs": bool(numbers),
            "warnings": [
                "Notebook outputs are saved artifacts, not independently executed results"
            ],
        }
    anchors = []
    lines = text.splitlines()
    for start in range(0, len(lines), 28):
        body = "\n".join(lines[start : start + 28])
        if body.strip():
            anchors.append(anchor(artifact, body, line=start + 1))
    parsed = {"text": text[:250000], "anchors": anchors[:200], "warnings": []}
    if ext == ".py":
        parsed["code"] = code_profile(text)
    if ext == ".r":
        parsed["code"] = {
            "supported": False,
            "reason": "R execution is outside the supported Python CPU profile",
        }
    if ext in {".json", ".jsonl", ".yaml", ".yml", ".toml"}:
        try:
            value = (
                json.loads(text)
                if ext == ".json"
                else [json.loads(x) for x in text.splitlines()[:100] if x.strip()]
                if ext == ".jsonl"
                else tomllib.loads(text)
                if ext == ".toml"
                else yaml.safe_load(text)
            )
            parsed["structured"] = value
            parsed["numbers"] = flatten_numbers(value)
            if ext in {".json", ".jsonl"} and artifact.kind == "data":
                from .checks import metric_name

                if any(
                    metric_name(n["key"])
                    in {"accuracy", "auc", "f1", "precision", "recall", "rmse", "mae", "r2"}
                    for n in parsed["numbers"]
                ):
                    parsed["role_hint"] = "results"
        except (ValueError, yaml.YAMLError):
            parsed["warnings"].append("Structured data could not be decoded")
    return parsed


def parse_pdf(artifact, data):
    import pdfplumber

    anchors, pages, warnings, tables, page_details = [], [], [], [], []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        budget = getattr(artifact, "page_budget", None)
        budget = settings().max_pdf_pages if budget is None else max(0, budget)
        if len(pdf.pages) > budget:
            warnings.append(
                f"Case PDF page budget: only {budget} pages of this document were inspected"
            )
        for n, page in enumerate(pdf.pages[:budget], 1):
            text = page.extract_text(x_tolerance=1.5) or ""
            pages.append(text)
            page_details.append(
                {
                    "page": n,
                    "width": page.width,
                    "height": page.height,
                    "low_text": len(text.strip()) < 35,
                }
            )
            if len(text.strip()) < 35:
                warnings.append(f"Page {n}: insufficient extractable text; OCR required")
                continue
            for start in range(0, len(text), 2400):
                anchors.append(anchor(artifact, text[start : start + 2400], page=n))
            if n <= 30:
                for table in page.find_tables()[:8]:
                    rows = table.extract()
                    tables.append({"page": n, "rows": rows, "bbox": list(table.bbox)})
                    table_anchor = anchor(artifact, json.dumps(rows), page=n, kind="table")
                    table_anchor["bbox"] = list(table.bbox)
                    anchors.append(table_anchor)
    return {
        "text": "\n\n".join(pages),
        "anchors": anchors,
        "tables": tables,
        "pages": len(pages),
        "page_details": page_details,
        "warnings": warnings,
    }


def parse_csv(artifact, text, ext):
    frame = pd.read_csv(io.StringIO(text), sep="\t" if ext == ".tsv" else ",", nrows=50001)
    sampled = len(frame) > 50000
    if sampled:
        frame = frame.head(50000)
    if len(frame.columns) > 500:
        frame = frame.iloc[:, :500]
    columns = []
    for name in frame.columns:
        series = frame[name]
        col = {
            "name": str(name),
            "dtype": str(series.dtype),
            "missing": int(series.isna().sum()),
            "unique": int(series.nunique()),
            "examples": [str(x)[:80] for x in series.dropna().head(3)],
        }
        if pd.api.types.is_numeric_dtype(series) and len(series.dropna()):
            col.update(min=float(series.min()), max=float(series.max()))
        columns.append(col)
    ids = [
        str(c)
        for c in frame.columns
        if re.search(
            r"(^id$|_id$|^subject$|^patient$|^person$|^entity$|^participant$)", str(c), re.I
        )
    ]
    profile = {
        "rows": len(frame),
        "sampled": sampled,
        "columns": columns,
        "entity_columns": ids,
        "repeated_entities": {c: int(frame[c].duplicated().sum()) for c in ids},
        "duplicate_rows": int(frame.duplicated().sum()),
    }
    from decimal import Decimal

    names = sorted(
        str(c) for c in frame.columns if str(c).lower() not in {"split", "partition", "fold"}
    )

    def scalar(value):
        if pd.isna(value):
            return ["missing"]
        if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
            value, (bool, np.bool_)
        ):
            return ["number", str(Decimal(str(value)).normalize())]
        return [type(value).__name__, str(value)]

    hashed = frame[names].head(20000)
    hashes = [
        hashlib.sha256(
            json.dumps([scalar(v) for v in row], ensure_ascii=False).encode()
        ).hexdigest()[:32]
        for row in hashed.itertuples(index=False, name=None)
    ]
    profile.update(
        fingerprint_columns=names, row_hashes=hashes, fingerprint_sampled=len(frame) > 20000
    )
    partition = next((c for c in frame.columns if str(c).lower() in {"split", "partition"}), None)
    if partition:
        profile["partition_hashes"] = {
            str(label).lower(): [
                h for h, v in zip(hashes, frame[partition].head(20000)) if str(v) == str(label)
            ]
            for label in frame[partition].dropna().unique()[:10]
        }
    profile["time_columns"] = []
    for c in frame.columns:
        if re.search(r"(^date$|_date$|timestamp|^time$|^year$|_time$)", str(c), re.I):
            values = frame[c].dropna().head(1000)
            if len(values):
                parsed_time = pd.to_datetime(
                    values.astype(str), errors="coerce", format="mixed", utc=True
                )
                if parsed_time.notna().mean() > 0.9:
                    profile["time_columns"].append(
                        {
                            "column": str(c),
                            "min": str(parsed_time.min()),
                            "max": str(parsed_time.max()),
                            "monotonic": bool(parsed_time.is_monotonic_increasing),
                        }
                    )
    summary = f"Dataset: {artifact.path}\nRows inspected: {len(frame)}{' (sample)' if sampled else ''}\nColumns: {', '.join(map(str, frame.columns))}\nRepeated entity rows: {profile['repeated_entities']}\nDuplicate rows: {profile['duplicate_rows']}"
    numbers = []
    from .checks import metric_name

    detected_results = {"y_true", "y_pred"}.issubset(frame.columns) or (
        any(
            metric_name(str(c)) in {"accuracy", "auc", "f1", "rmse", "mae", "r2"}
            for c in frame.columns
        )
        and any(c in frame for c in ("dataset", "model", "split", "run"))
    )
    if artifact.kind == "results" or detected_results:
        for i, row in frame.head(100).iterrows():
            for key, value in row.items():
                if isinstance(value, (float, int, np.number)) and pd.notna(value):
                    numbers.append(
                        {
                            "key": str(key),
                            "value": float(value),
                            "pointer": f"row/{i}/{key}",
                            "line": int(i) + 2,
                            "context": {str(k): str(v) for k, v in row.items() if k != key},
                        }
                    )
        if (
            {"y_true", "y_pred"}.issubset(frame.columns)
            and not sampled
            and not frame[["y_true", "y_pred"]].isna().any().any()
            and frame["y_true"].nunique() <= 50
        ):
            context = {
                c: str(frame[c].iloc[0])
                for c in ("dataset", "model", "split", "averaging", "seed")
                if c in frame and frame[c].nunique() == 1
            }
            numbers.append(
                {
                    "key": "accuracy",
                    "value": float((frame["y_true"] == frame["y_pred"]).mean()),
                    "pointer": "computed/accuracy(y_true,y_pred)",
                    "context": context,
                    "derived": True,
                    "rows": len(frame),
                }
            )
    return {
        "text": summary,
        "anchors": [anchor(artifact, summary, line=1, kind="dataset")],
        "profile": profile,
        "numbers": numbers,
        "role_hint": "results" if detected_results else artifact.kind,
        "warnings": ["Dataset profiling limited to 50,000 rows"] if sampled else [],
    }


def flatten_numbers(value, pointer="", inherited=None):
    result = []
    if isinstance(value, dict):
        context = {
            str(k): str(v)
            for k, v in value.items()
            if isinstance(v, (str, bool))
            or (k in {"seed", "run", "fold", "trial"} and isinstance(v, (int, float)))
        }
        context = {**(inherited or {}), **context}
        for key, val in value.items():
            pos = pointer + "/" + str(key).replace("~", "~0").replace("/", "~1")
            if isinstance(val, (float, int)) and not isinstance(val, bool):
                number_context = dict(context)
                for averaging in ("macro", "micro", "weighted"):
                    if re.search(rf"(?:_|-){averaging}$", str(key), re.I):
                        number_context["averaging"] = averaging
                result.append(
                    {
                        "key": str(key),
                        "value": float(val),
                        "pointer": pos,
                        "context": number_context,
                    }
                )
            elif isinstance(val, (dict, list)):
                result.extend(flatten_numbers(val, pos, context))
    elif isinstance(value, list):
        for i, val in enumerate(value[:1000]):
            result.extend(flatten_numbers(val, f"{pointer}/{i}", inherited))
    return result[:2000]


def literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None


def code_profile(text):
    result = {
        "imports": [],
        "calls": [],
        "datasets": [],
        "target": None,
        "features": None,
        "feature_exclusions": None,
        "split": None,
        "seed": None,
        "test_size": 0.25,
        "estimator": None,
        "params": {},
        "scaling": False,
        "stratify": False,
        "preprocessors": [],
        "unresolved_settings": [],
        "preprocessing_before_split": False,
        "supported": True,
    }
    try:
        tree = ast.parse(text)
    except SyntaxError:
        result["supported"] = False
        result["reason"] = "Python AST could not be parsed"
        return result
    split_line, fit_lines = None, []
    constants = {}
    assigned = set()
    reassigned = set()
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
        ):
            name = statement.targets[0].id
            if name in assigned:
                reassigned.add(name)
            assigned.add(name)
            value = literal(statement.value)
            if value is not None:
                constants[name] = value
    for name in reassigned:
        constants.pop(name, None)

    def resolve(node):
        return constants.get(node.id) if isinstance(node, ast.Name) else literal(node)

    estimators = []
    split_count = 0
    supported_estimators = {
        "LogisticRegression",
        "RandomForestClassifier",
        "DecisionTreeClassifier",
        "LinearRegression",
        "Ridge",
        "RandomForestRegressor",
    }
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = node.module if isinstance(node, ast.ImportFrom) else node.names[0].name
            result["imports"].append(module)
            if module and module.split(".")[0] in {"torch", "tensorflow", "jax"}:
                result["supported"] = False
                result["reason"] = "Deep-learning execution is outside the CPU support profile"
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Subscript) and (
                isinstance(node.value.slice, (ast.Compare, ast.BoolOp))
                or (isinstance(node.value.slice, ast.Name) and resolve(node.value.slice) is None)
            ):
                result["unresolved_settings"].append("unmapped row/column filtering")
            if any(isinstance(x, ast.Name) and x.id in {"X", "features"} for x in node.targets):
                if isinstance(node.value, ast.Subscript):
                    names = resolve(node.value.slice)
                    if isinstance(names, list) and all(isinstance(x, str) for x in names):
                        result["features"] = names
                if (
                    isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and node.value.func.attr == "drop"
                ):
                    kw = {k.arg: resolve(k.value) for k in node.value.keywords}
                    columns = kw.get("columns")
                    if columns is None and kw.get("axis") == 1 and node.value.args:
                        columns = resolve(node.value.args[0])
                    if isinstance(columns, str):
                        columns = [columns]
                    if isinstance(columns, list) and all(isinstance(c, str) for c in columns):
                        result["feature_exclusions"] = columns
            if any(
                isinstance(x, ast.Name) and x.id in {"y", "target", "labels"} for x in node.targets
            ):
                if (
                    isinstance(node.value, ast.Subscript)
                    and isinstance(node.value.slice, ast.Constant)
                    and isinstance(node.value.slice.value, str)
                ):
                    result["target"] = node.value.slice.value
                elif isinstance(node.value, ast.Attribute):
                    result["target"] = node.value.attr
        if isinstance(node, ast.Call):
            name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else node.func.id
                if isinstance(node.func, ast.Name)
                else ""
            )
            kwargs = {k.arg: resolve(k.value) for k in node.keywords if k.arg}
            result["calls"].append({"name": name, "line": node.lineno, "kwargs": kwargs})
            if (
                name in {"read_csv", "read_table"}
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                result["datasets"].append(str(node.args[0].value))
            if name == "train_test_split":
                split_count += 1
                result["split"] = "random"
                split_line = node.lineno
                result["seed"] = kwargs.get("random_state")
                result["test_size"] = kwargs.get("test_size", 0.25)
                if "stratify" in kwargs:
                    value = next(k.value for k in node.keywords if k.arg == "stratify")
                    if isinstance(value, ast.Name) and value.id in {"y", "labels", "target"}:
                        result["stratify"] = True
                    elif not isinstance(value, ast.Constant) or value.value is not None:
                        result["unresolved_settings"].append("stratification expression")
                if kwargs.get("shuffle") is False or "train_size" in kwargs:
                    result["unresolved_settings"].append("nonstandard split settings")
                if any(
                    k.arg != "stratify"
                    and resolve(k.value) is None
                    and not (isinstance(k.value, ast.Constant) and k.value.value is None)
                    for k in node.keywords
                ):
                    result["unresolved_settings"].append("unresolved split parameter")
            if name in {"GroupKFold", "GroupShuffleSplit"}:
                result["split"] = "group"
            if name == "TimeSeriesSplit":
                result["split"] = "temporal"
            if name in supported_estimators:
                estimators.append(name)
                result["estimator"] = name
                result["params"] = kwargs
                if node.args or any(
                    k.arg is None
                    or (
                        resolve(k.value) is None
                        and not (isinstance(k.value, ast.Constant) and k.value.value is None)
                    )
                    for k in node.keywords
                ):
                    result["unresolved_settings"].append("unresolved estimator arguments")
            if name in {
                "StandardScaler",
                "MinMaxScaler",
                "SimpleImputer",
                "PCA",
                "OneHotEncoder",
                "OrdinalEncoder",
                "PolynomialFeatures",
                "SelectKBest",
                "get_dummies",
            }:
                result["preprocessors"].append(name)
                if name == "StandardScaler":
                    result["scaling"] = True
                if name == "SimpleImputer":
                    result["imputer_strategy"] = kwargs.get("strategy", "mean")
                if name not in {"StandardScaler", "SimpleImputer", "OneHotEncoder", "get_dummies"}:
                    result["unresolved_settings"].append("unsupported transformation: " + name)
                if name == "OneHotEncoder" and kwargs.get("drop") is not None:
                    result["unresolved_settings"].append("one-hot dropped categories")
                if name == "OneHotEncoder" and (
                    kwargs.get("handle_unknown") != "ignore"
                    or kwargs.get("categories", "auto") != "auto"
                ):
                    result["unresolved_settings"].append("unmapped category policy")
            if name in {
                "query",
                "dropna",
                "merge",
                "join",
                "concat",
                "groupby",
                "resample",
                "shift",
                "rolling",
                "cross_val_score",
                "cross_validate",
                "GridSearchCV",
                "RandomizedSearchCV",
            }:
                result["unresolved_settings"].append("unmapped data/evaluation operation: " + name)
            if name == "fit_transform":
                fit_lines.append(node.lineno)
    result["preprocessing_before_split"] = bool(
        split_line and any(line < split_line for line in fit_lines)
    )
    if len(estimators) > 1:
        result["supported"] = False
        result["reason"] = (
            "Multiple estimator definitions in this source need experiment-level mapping"
        )
    if split_count > 1:
        result["unresolved_settings"].append("multiple split definitions")
    from .source_analysis import extra_profile

    result.update(extra_profile(tree, result["target"]))
    if result["cv"]:
        result["split"] = "cv"
        result["unresolved_settings"] = [
            x
            for x in result["unresolved_settings"]
            if x
            not in {
                "unmapped data/evaluation operation: cross_val_score",
                "unmapped data/evaluation operation: cross_validate",
            }
        ]
    if result["unresolved_settings"]:
        result["supported"] = False
        result["reason"] = "Scientific operations require mapping: " + ", ".join(
            sorted(set(result["unresolved_settings"]))
        )
    return result
