"""Original CPU program harness. This file runs only inside a disposable sandbox."""

import ast
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import time


def supported_source(text, local_modules=()):
    tree = ast.parse(text)
    allowed = {
        "numpy",
        "pandas",
        "sklearn",
        "scipy",
        "math",
        "statistics",
        "json",
        "csv",
        "pathlib",
        "os",
        "sys",
        "time",
        "warnings",
        "collections",
        "itertools",
        "functools",
        "random",
        "typing",
        "matplotlib",
        "seaborn",
        "argparse",
        "copy",
        "re",
        *local_modules,
    }
    denied = {
        "eval",
        "exec",
        "compile",
        "__import__",
        "system",
        "popen",
        "Popen",
        "spawn",
        "fork",
        "chmod",
        "chown",
        "unlink",
        "remove",
        "rmdir",
        "rmtree",
        "getattr",
        "setattr",
        "delattr",
        "globals",
        "locals",
        "vars",
        "breakpoint",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(n.name.split(".")[0] not in allowed for n in node.names):
                raise ValueError(
                    "Original source imports a dependency outside the preinstalled CPU profile"
                )
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] not in allowed
        ):
            raise ValueError("Original source imports an unsupported dependency")
        if isinstance(node, ast.Call):
            function = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if function in denied:
                raise ValueError(
                    "Original source contains an unsupported dynamic, filesystem mutation or process operation: "
                    + function
                )
        if isinstance(node, ast.Attribute) and (
            node.attr.startswith("_")
            or node.attr in {"modules", "settrace", "setprofile", "addaudithook"}
        ):
            raise ValueError("Reflective source is outside the supported profile")
    return tree


def evaluate_original(payload):
    if os.environ.get("CB_ISOLATED_EXECUTION") != "1":
        raise RuntimeError("Original source may run only inside an isolated execution environment")
    started = time.monotonic()
    files = payload["spec"]["source_files"]
    if len(files) > 200:
        raise ValueError("Original-program file budget exceeded")
    with tempfile.TemporaryDirectory(prefix="claimbreaker-original-") as directory:
        root = Path(directory)
        sources, total = {}, 0
        for item in files:
            name = PurePosixPath(item["path"])
            if (
                name.is_absolute()
                or ".." in name.parts
                or "\\" in item["path"]
                or any(p.startswith(".env") for p in name.parts)
                or any(p.startswith("__claimbreaker_") for p in name.parts)
                or str(root.joinpath(*name.parts)) in sources
            ):
                raise ValueError("Unsafe original source path")
            data = base64.b64decode(item["data"], validate=True)
            total += len(data)
            if total > 50 * 1024**2:
                raise ValueError("Original-program byte budget exceeded")
            path = root.joinpath(*name.parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            sources[str(path)] = hashlib.sha256(data).hexdigest()
        local = {
            PurePosixPath(f["path"]).parts[0].removesuffix(".py")
            for f in files
            if f["path"].endswith(".py")
        }
        entry = root / payload["spec"]["entry_path"]
        if str(entry) not in sources or entry.suffix not in {".py", ".ipynb"}:
            raise ValueError("Entry point is not an immutable supplied Python/notebook source")
        repairs = []
        if entry.suffix == ".ipynb":
            notebook = json.loads(entry.read_text())
            cells = []
            for cell in notebook.get("cells", []):
                if cell.get("cell_type") != "code":
                    continue
                source = (
                    "".join(cell.get("source", []))
                    if isinstance(cell.get("source"), list)
                    else cell.get("source", "")
                )
                lines = []
                for line in source.splitlines():
                    if line.strip() in {"%matplotlib inline", "%matplotlib notebook"}:
                        repairs.append("Removed notebook display-only matplotlib magic")
                        continue
                    if line.lstrip().startswith(("%", "!")):
                        raise ValueError("Notebook contains an unsupported magic or shell command")
                    lines.append(line)
                cells.append("\n".join(lines))
            entry = root / "__claimbreaker_notebook__.py"
            entry.write_text("\n\n".join(cells))
            sources[str(entry)] = hashlib.sha256(entry.read_bytes()).hexdigest()
        for path in sources:
            if path.endswith(".py"):
                supported_source(Path(path).read_text(), local)
        for path in sources:
            Path(path).chmod(0o444)
        manifest = root / "__claimbreaker_manifest__.json"
        manifest.write_text(
            json.dumps(
                {
                    "entry": str(entry),
                    "root": str(root),
                    "sources": sources,
                    "local_modules": list(local),
                    "entity": payload["spec"].get("entity"),
                }
            )
        )
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/tmp",
            "CB_ISOLATED_EXECUTION": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "MPLBACKEND": "Agg",
        }
        process = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).resolve()), "child", str(manifest)],
            capture_output=True,
            timeout=80,
            env=env,
            cwd=entry.parent,
        )
        if process.returncode:
            raise RuntimeError(
                "Original program failed: " + process.stderr.decode(errors="replace")[-1800:]
            )
        result = json.loads(process.stdout)
        after = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in sources}
        if sources != after:
            raise RuntimeError("Original source changed during execution; measurements rejected")
        if not result.get("metrics"):
            raise ValueError(
                "Original program completed but no supported measured metric was captured"
            )
        result.update(
            classification="original_execution",
            seconds=round(time.monotonic() - started, 3),
            source_hashes={str(Path(p).relative_to(root)): h for p, h in after.items()},
            repairs=repairs + result.get("repairs", []),
            helper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            limitations=[
                "Original code ran in isolation with metric instrumentation; publication comparability still depends on protocol, dataset, version and human correspondence",
                "No dependencies were installed and no scientific settings were repaired",
            ],
        )
        return result


def child(manifest_path):
    import contextlib
    import functools
    import inspect
    import resource
    import signal
    import runpy

    resource.setrlimit(resource.RLIMIT_CPU, (65, 70))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024**2, 8 * 1024**2))
    signal.signal(
        signal.SIGALRM,
        lambda *_: (_ for _ in ()).throw(TimeoutError("Original execution timed out")),
    )
    signal.alarm(75)
    manifest = json.loads(Path(manifest_path).read_text())
    root, entry = Path(manifest["root"]), Path(manifest["entry"])
    import numpy as np
    import pandas as pd
    import sklearn
    import sklearn.metrics as measures
    import sklearn.model_selection as selection

    events, folds, repairs = [], [], []
    measured = {}
    for metric in (
        "accuracy_score",
        "f1_score",
        "roc_auc_score",
        "precision_score",
        "recall_score",
        "mean_squared_error",
        "root_mean_squared_error",
        "r2_score",
    ):
        function = getattr(measures, metric, None)
        if function is None:
            continue

        def instrument(fn, metric_name):
            @functools.wraps(fn)
            def record(*args, **kwargs):
                value = fn(*args, **kwargs)
                key = {
                    "accuracy_score": "accuracy",
                    "roc_auc_score": "auc",
                    "mean_squared_error": "mse",
                    "root_mean_squared_error": "rmse",
                    "r2_score": "r2",
                }.get(metric_name, metric_name.removesuffix("_score"))
                if key in {"f1", "precision", "recall"}:
                    key += "_" + str(kwargs.get("average", "binary"))
                if np.isscalar(value) and np.isfinite(value):
                    measured[key] = float(value)
                    location = next(
                        (
                            f
                            for f in inspect.stack(context=0)
                            if str(f.filename).startswith(str(root)) and f.filename != __file__
                        ),
                        None,
                    )
                    events.append(
                        {
                            "metric": key,
                            "value": float(value),
                            "path": str(Path(location.filename).relative_to(root))
                            if location
                            else None,
                            "line": location.lineno if location else None,
                        }
                    )
                return value

            return record

        setattr(measures, metric, instrument(function, metric))
    for operation in ("cross_val_score", "cross_validate"):
        function = getattr(selection, operation)

        def capture(fn):
            @functools.wraps(fn)
            def record(*args, **kwargs):
                value = fn(*args, **kwargs)
                scores = value if isinstance(value, np.ndarray) else value.get("test_score")
                if scores is not None:
                    scoring = kwargs.get("scoring") or (
                        "r2" if sklearn.base.is_regressor(args[0]) else "accuracy"
                    )
                    key = str(scoring)
                    if key == "neg_root_mean_squared_error":
                        key = "rmse"
                        scores = -scores
                    folds.append(
                        {
                            "metric": key,
                            "values": np.asarray(scores).tolist(),
                            "mean": float(np.mean(scores)),
                            "std": float(np.std(scores)),
                            "n_folds": len(scores),
                        }
                    )
                    measured[key] = float(np.mean(scores))
                return value

            return record

        setattr(selection, operation, capture(function))
    original_read = pd.read_csv
    loaded_frames, split_indices = [], []

    def read_csv(path, *args, **kwargs):
        if isinstance(path, (str, Path)) and not Path(path).exists():
            matches = list(root.rglob(Path(path).name))
            if len(matches) == 1:
                repairs.append("Resolved missing dataset path by unique filename: " + str(path))
                path = matches[0]
        frame = original_read(path, *args, **kwargs)
        if isinstance(frame, pd.DataFrame):
            loaded_frames.append(frame)
        return frame

    pd.read_csv = read_csv
    original_split = selection.train_test_split

    @functools.wraps(original_split)
    def split(*args, **kwargs):
        value = original_split(*args, **kwargs)
        if (
            len(value) >= 2
            and isinstance(value[0], pd.DataFrame)
            and isinstance(value[1], pd.DataFrame)
        ):
            split_indices.append((value[0].index, value[1].index))
        return value

    selection.train_test_split = split
    immutable = set(manifest["sources"]) | {str(Path(manifest_path).resolve())}

    def audit(event, args):
        if event == "open" and args and isinstance(args[0], (str, bytes)):
            path = str(Path(os.fsdecode(args[0])).resolve())
            mode = args[1] if len(args) > 1 else "r"
            flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
            writing = (
                isinstance(mode, str)
                and any(c in mode for c in "wa+")
                or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
            )
            if path in immutable and writing:
                raise PermissionError("Original source snapshot is immutable")
            if writing and not Path(path).is_relative_to(root):
                raise PermissionError(
                    "Generated output must remain inside the isolated project directory"
                )
        if event.startswith(("socket.", "subprocess.", "os.system", "os.exec", "os.spawn")):
            raise PermissionError("Original-program network/process operations are disabled")

    sys.addaudithook(audit)
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(entry.parent))
    sys.argv = [str(entry)]

    class Log(io.StringIO):
        def write(self, text):
            return super().write(text[: max(0, 65536 - self.tell())])

    log = Log()
    with contextlib.redirect_stdout(log):
        runpy.run_path(str(entry), run_name="__main__")
    overlap = None
    if manifest.get("entity") and split_indices:
        train, test = split_indices[-1]
        candidates = [
            frame
            for frame in loaded_frames
            if manifest["entity"] in frame
            and frame.index.is_unique
            and set(train).union(test).issubset(frame.index)
        ]
        if len(candidates) == 1:
            frame = candidates[0]
            overlap = len(
                set(frame.loc[train, manifest["entity"]]) & set(frame.loc[test, manifest["entity"]])
            )
    print(
        json.dumps(
            {
                "metrics": measured,
                "metric_events": events[-100:],
                "folds": folds,
                "repairs": repairs,
                "stdout": log.getvalue(),
                "entity_overlap": overlap,
                "train_rows": len(split_indices[-1][0]) if split_indices else None,
                "test_rows": len(split_indices[-1][1]) if split_indices else None,
                "environment": {
                    "python": sys.version.split()[0],
                    "sklearn": sklearn.__version__,
                    "pandas": pd.__version__,
                    "numpy": np.__version__,
                },
            },
            allow_nan=False,
        )
    )


if __name__ == "__main__" and len(sys.argv) > 2 and sys.argv[1] == "child":
    if os.environ.get("CB_ISOLATED_EXECUTION") != "1":
        raise RuntimeError("Isolation required")
    child(sys.argv[2])
