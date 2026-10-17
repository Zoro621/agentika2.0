from types import SimpleNamespace
import json
from claimbreaker.parsing import parse
from claimbreaker.protocol_checks import protocol_checks
from claimbreaker.execution import execution_plan, execution_questions


def art(id, path, kind, body):
    return {
        "id": id,
        "path": path,
        "kind": kind,
        "parsed": parse(SimpleNamespace(id=id, path=path, kind=kind), body.encode()),
    }


def test_paper_seed_difference_is_qualified():
    p = art(
        "p", "paper.md", "documentation", "Methods: random seed of 17 and a 25% test partition."
    )
    c = art(
        "c",
        "train.py",
        "code",
        "train_test_split(X,y,test_size=.25,random_state=42)\nmodel=RandomForestClassifier(n_estimators=80)",
    )
    findings, checks = protocol_checks([p, c])
    assert findings[0]["evidence_status"] == "supported_concern"
    assert any(c["status"] == "passed" for c in checks)


def test_missing_trial_records_is_not_a_contradiction():
    p = art("p", "paper.md", "documentation", "We ran 10 independent trials.")
    c = art("c", "train.py", "code", "model=RandomForestClassifier()")
    r = art(
        "r",
        "results.json",
        "results",
        json.dumps({"runs": [{"accuracy": 0.8}, {"accuracy": 0.81}]}),
    )
    f, checks = protocol_checks([p, c, r])
    assert not f and checks[0]["status"] == "inconclusive"


def test_predictions_are_recomputed_from_supplied_rows():
    p = art(
        "r",
        "predictions.csv",
        "results",
        "y_true,y_pred,dataset,split\n1,1,cohort,test\n0,1,cohort,test\n1,1,cohort,test\n0,0,cohort,test\n",
    )
    metric = next(x for x in p["parsed"]["numbers"] if x["key"] == "accuracy")
    assert metric["value"] == 0.75 and metric["context"]["dataset"] == "cohort"


def test_ambiguous_entrypoints_become_human_choices():
    code = 'data=pd.read_csv("data.csv")\nX=data[["signal"]]\ny=data["outcome"]\ntrain_test_split(X,y,random_state=42)\nmodel=LogisticRegression()'
    a = art("a", "train_a.py", "code", code)
    b = art("b", "train_b.py", "code", code)
    d = art("d", "data.csv", "data", "signal,outcome\n1,0\n2,1\n3,0\n4,1\n")
    q = execution_questions([a, b, d], [])
    assert q[0]["id"] == "experiment-entry"
    plans, reason = execution_plan([a, b, d], [{"question_id": "experiment-entry", "answer": "b"}])
    assert reason is None and plans[0]["code_id"] == "b"
