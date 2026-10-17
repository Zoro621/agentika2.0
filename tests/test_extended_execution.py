import numpy as np
import pandas as pd
import pytest
from claimbreaker.sandbox_worker import evaluate
from claimbreaker.original_worker import supported_source, evaluate_original


def payload():
    rng=np.random.default_rng(12)
    data=pd.DataFrame({"x":rng.normal(size=100),"z":rng.normal(size=100),"person_id":np.repeat(np.arange(20),5),"date":pd.date_range("2020-01-01",periods=100).astype(str)})
    data["outcome"]=(data.x+data.z>0).astype(int)
    return {"csv":data.to_csv(index=False),"spec":{"target":"outcome","features":["x","z"],"estimator":"LogisticRegression","params":{"C":1,"max_iter":200},"seed":42,"test_size":0.25,"variant":"baseline","entity":"person_id","cv":{"folds":4,"kind":"StratifiedKFold","shuffle":True,"seed":7,"scoring":"accuracy"}}}


def test_cv_has_real_fold_measurements_and_mean():
    result=evaluate(payload())
    assert len(result["folds"])==4
    assert result["metrics"]["accuracy"]==pytest.approx(np.mean([r["metrics"]["accuracy"] for r in result["folds"]]))
    assert all(r["train_rows"]==75 and r["test_rows"]==25 for r in result["folds"])


def test_grouped_cv_has_no_entity_overlap():
    job=payload();job["spec"].update(variant="grouped",split_mode="grouped")
    result=evaluate(job)
    assert result["entity_overlap"]==0 and result["classification"]=="corrected_protocol"


def test_temporal_correction_uses_order_and_does_not_drop_unknown_dates():
    job=payload();job["spec"].update(cv=None,variant="temporal",time_column="date")
    result=evaluate(job)
    assert result["test_rows"]==25
    job["csv"]=job["csv"].replace("2020-01-01","unparseable")
    with pytest.raises(ValueError,match="complete interpretable"): evaluate(job)


def test_original_source_validation_never_executes_it():
    supported_source('raise RuntimeError("data only")')
    with pytest.raises(ValueError): supported_source('import subprocess\nsubprocess.run(["whoami"])')
    with pytest.raises(RuntimeError,match="isolated"): evaluate_original({})
