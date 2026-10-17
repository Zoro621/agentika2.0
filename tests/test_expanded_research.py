import json
from types import SimpleNamespace
from claimbreaker.parsing import parse, code_profile
from claimbreaker.research_checks import expanded_checks
from claimbreaker.pdf_tools import render_page
from claimbreaker.samples import build_sample
import io
import zipfile


def artifact(id, path, body):
    a = SimpleNamespace(id=id, path=path, kind="data" if path.endswith("csv") else "code")
    return {"id": id, "path": path, "kind": a.kind, "parsed": parse(a, body.encode())}


def test_partition_overlap_is_measured_with_matching_schemas():
    a = artifact("a", "train.csv", "x,y\n1,0\n2,1\n")
    b = artifact("b", "test.csv", "x,y\n2.0,1\n3.0,0\n")
    findings, checks, _ = expanded_checks([a, b], [])
    assert findings[0]["observed"]["overlap"] == 1
    assert checks[0]["status"] == "flagged"


def test_clean_partitions_are_not_flagged():
    a = artifact("a", "train.csv", "x,y\n1,0\n2,1\n")
    b = artifact("b", "test.csv", "x,y\n3,0\n4,1\n")
    findings, checks, _ = expanded_checks([a, b], [])
    assert not findings and checks[0]["status"] == "passed"


def test_explicit_partition_column_excludes_partition_label_from_observation():
    a = artifact("a", "data.csv", "x,y,split\n1,0,train\n1,0,test\n")
    findings, _, _ = expanded_checks([a], [])
    assert findings[0]["observed"]["overlap"] == 1


def test_cv_profile_preserves_explicit_splitter():
    source = 'X = data[["x"]]\ny = data["y"]\ncv = StratifiedKFold(n_splits=4, shuffle=True, random_state=9)\nmodel = LogisticRegression(C=2)\nscores = cross_val_score(model, X, y, cv=cv, scoring="accuracy")'
    p = code_profile(source)
    assert p["supported"] and p["cv"]["folds"] == 4 and p["cv"]["seed"] == 9


def test_source_flow_has_exact_fit_and_split_anchors():
    a = artifact(
        "c",
        "train.py",
        'scaler = StandardScaler()\nX = data[["x"]]\ny = data["y"]\nX = scaler.fit_transform(X)\ntrain_test_split(X,y)',
    )
    findings, _, _ = expanded_checks([a], [])
    assert findings[0]["kind"] == "preprocessing_flow"
    assert findings[0]["evidence"][0]["highlight_line"] == 4


def test_page_renderer_returns_original_with_word_highlights():
    archive = zipfile.ZipFile(io.BytesIO(build_sample("paper")))
    result = render_page(archive.read("paper.pdf"), 1, "Test accuracy")
    assert result["image"].startswith("data:image/png;base64,") and result["boxes"]
