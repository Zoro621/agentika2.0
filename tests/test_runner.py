import numpy as np
import pandas as pd
import pytest
from claimbreaker.sandbox_worker import evaluate


def test_real_grouped_re_evaluation():
    rng = np.random.default_rng(9)
    frame = pd.DataFrame(np.repeat(rng.normal(size=(120, 5)), 8, axis=0), columns=list("abcde"))
    frame["person_id"] = np.repeat(np.arange(120), 8)
    frame["outcome"] = np.repeat(rng.integers(0, 2, 120), 8)
    spec = {
        "target": "outcome",
        "features": list("abcde"),
        "variant": "baseline",
        "estimator": "RandomForestClassifier",
        "params": {"n_estimators": 60},
        "seed": 42,
        "test_size": 0.25,
        "entity": "person_id",
    }
    original = evaluate({"csv": frame.to_csv(index=False), "spec": spec})
    grouped = evaluate({"csv": frame.to_csv(index=False), "spec": {**spec, "variant": "grouped"}})
    assert original["entity_overlap"] > 0 and grouped["entity_overlap"] == 0
    assert original["metrics"]["accuracy"] > grouped["metrics"]["accuracy"] + 0.15
    assert original["classification"] == "reconstruction"
    assert grouped["classification"] == "corrected_protocol"


def test_unknown_estimator_rejected():
    with pytest.raises(ValueError):
        evaluate(
            {
                "csv": "x,y\n0,1\n1,0\n2,1\n3,0\n4,1\n5,0\n",
                "spec": {
                    "target": "y",
                    "features": ["x"],
                    "variant": "baseline",
                    "estimator": "os.system",
                    "seed": 42,
                },
            }
        )


def test_parameters_are_not_silently_changed():
    with pytest.raises(ValueError, match="not silently changed"):
        evaluate(
            {
                "csv": "x,y\n0,1\n1,0\n2,1\n3,0\n4,1\n5,0\n",
                "spec": {
                    "target": "y",
                    "features": ["x"],
                    "variant": "baseline",
                    "estimator": "RandomForestClassifier",
                    "params": {"n_estimators": 500},
                    "seed": 42,
                },
            }
        )
