import numpy as np
import pandas as pd
from claimbreaker.sandbox_worker import evaluate
from claimbreaker.run_checks import execution_checks


def test_human_semantics_and_actual_outputs_bound_the_conclusion():
    rng = np.random.default_rng(19)
    frame = pd.DataFrame(np.repeat(rng.normal(size=(100, 3)), 8, axis=0), columns=["a", "b", "c"])
    frame["person_id"] = np.repeat(np.arange(100), 8)
    frame["y"] = np.repeat(rng.integers(0, 2, 100), 8)
    spec = {
        "target": "y",
        "features": ["a", "b", "c"],
        "estimator": "RandomForestClassifier",
        "params": {"n_estimators": 40},
        "seed": 42,
        "entity": "person_id",
        "variant": "baseline",
    }
    runs = []
    for variant in ("baseline", "grouped"):
        out = evaluate({"csv": frame.to_csv(index=False), "spec": {**spec, "variant": variant}})
        runs.append(
            {
                "id": "test-" + variant,
                "status": "completed",
                "manifest": {"variant": variant, "input_sha256": out["dataset_sha256"]},
                "output": out,
            }
        )
    assert not execution_checks(runs, [])[0]
    findings, checks = execution_checks(
        runs, [{"question_id": "generalization", "answer": "new_entities"}]
    )
    assert findings[0]["observed"]["corrected_entity_overlap"] == 0
    assert all("execution_id" in e for e in findings[0]["evidence"])
    assert findings[0]["evidence_status"] == "supported_concern" and checks[0]["status"] == "passed"
