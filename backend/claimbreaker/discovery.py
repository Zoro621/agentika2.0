"""Give every source family coverage before filling the bounded inspection budget."""

from pathlib import PurePosixPath


def prioritize(artifacts, limit=100):
    def rank(artifact):
        path = artifact.path.lower()
        name = PurePosixPath(path).name
        entry = artifact.kind == "code" and any(
            word in name for word in ("train", "experiment", "evaluate", "main", "benchmark")
        )
        test = any(part in {"tests", "test"} for part in PurePosixPath(path).parts)
        return (not entry, test, artifact.size, path)

    buckets = {
        kind: sorted([a for a in artifacts if a.kind == kind], key=rank)
        for kind in ("paper", "configuration", "results", "code", "data", "documentation")
    }
    quotas = {
        "paper": 10,
        "configuration": 10,
        "results": 15,
        "code": 25,
        "data": 25,
        "documentation": 15,
    }
    selected = []
    for kind, bucket in buckets.items():
        selected.extend(bucket[: quotas[kind]])
    selected = selected[:limit]
    ids = {a.id for a in selected}
    remainder = sorted((a for a in artifacts if a.id not in ids), key=rank)
    return selected + remainder[: max(0, limit - len(selected))]
