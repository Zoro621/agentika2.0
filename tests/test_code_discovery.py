from types import SimpleNamespace
from claimbreaker.parsing import code_profile, parse
from claimbreaker.execution import execution_plan


def test_named_feature_list_and_stratification_are_discovered():
    profile = code_profile(
        'FEATURES=["a","b"]\nX=data[FEATURES]\ny=data["outcome"]\ntrain_test_split(X,y,random_state=42,stratify=y)\nmodel=LogisticRegression(C=1)'
    )
    assert profile["features"] == ["a", "b"] and profile["stratify"] is True


def test_drop_columns_maps_explicit_source_operation():
    source = 'data=pd.read_csv("data.csv")\nX=data.drop(columns=["outcome","person_id"])\ny=data["outcome"]\ntrain_test_split(X,y,random_state=42)\nmodel=LogisticRegression()'
    code = {"id": "c", "path": "train.py", "kind": "code", "parsed": {"code": code_profile(source)}}
    data = {
        "id": "d",
        "path": "data.csv",
        "kind": "data",
        "parsed": parse(
            SimpleNamespace(id="d", path="data.csv", kind="data"),
            b"person_id,a,outcome\n1,1,0\n2,2,1\n3,3,0\n4,4,1\n",
        ),
    }
    plans, reason = execution_plan([code, data], [])
    assert reason is None and plans[0]["features"] == ["a"]


def test_unmapped_transform_and_parameter_prevent_silent_changes():
    assert not code_profile("model=RandomForestClassifier(n_estimators=number_of_trees)")[
        "supported"
    ]
    assert not code_profile("model=LogisticRegression()\nreduced=PCA(n_components=2)")["supported"]
    assert not code_profile("model=LogisticRegression()\nother=RandomForestClassifier()")[
        "supported"
    ]


def test_source_filter_is_not_silently_ignored():
    assert not code_profile('data=data.query("age>18")\nmodel=LogisticRegression()')["supported"]
    assert not code_profile('data=data[data["age"]>18]\nmodel=LogisticRegression()')["supported"]


def test_literal_none_hyperparameter_is_preserved():
    profile = code_profile("model=RandomForestClassifier(max_features=None,random_state=42)")
    assert (
        profile["supported"]
        and "max_features" in profile["params"]
        and profile["params"]["max_features"] is None
    )
