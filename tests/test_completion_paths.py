import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace
import pytest
from claimbreaker.parsing import parse
from claimbreaker.checks import extract_claims
from claimbreaker.paper_checks import table_claims, extended_paper_checks
from claimbreaker.scientific_agent import grounded_question, apply_interpretations, investigate
from claimbreaker.schemas import InvestigationProposal
from claimbreaker.ocr import gate_ocr, verification_questions
from claimbreaker.db import initialize, Session, Case, Job, Execution, Artifact
from claimbreaker import storage
from claimbreaker.recovery import reconcile


def artifact(id, path, kind, text):
    a = SimpleNamespace(id=id, path=path, kind=kind)
    return dict(id=id, path=path, kind=kind, parsed=parse(a, text.encode()))


def test_table_value_has_page_cell_geometry_and_precision():
    a = artifact("p", "paper.md", "paper", "")
    a["parsed"]["tables"] = [
        dict(
            page=3,
            bbox=[10, 20, 200, 100],
            rows=[["Method", "Accuracy (%)"], ["Logistic regression", "91.2"]],
        )
    ]
    c = table_claims(a)[0]
    assert c["value"] == pytest.approx(0.912) and c["tolerance"] == pytest.approx(0.0005)
    assert c["anchor"]["page"] == 3 and c["anchor"]["row"] == 1 and c["anchor"]["column"] == 1
    assert c["anchor"]["bbox"] == [10, 20, 200, 100]


def test_trial_aggregation_requires_judgment_and_changes_real_arithmetic():
    p = artifact("p", "paper.md", "documentation", "Accuracy: 90.0%.")
    r = artifact("r", "results.json", "results", '{"trials":[{"accuracy":0.8},{"accuracy":1.0}]}')
    claims = extract_claims([p])
    c = claims[0]
    qid = "aggregation:" + c["id"]
    f, cx, q, handled = extended_paper_checks([p, r], claims, [])
    assert not f and cx[0]["status"] == "inconclusive" and c["id"] in handled
    decisions = [
        dict(question_id=qid, answer="mean"),
        dict(question_id="repository-version", answer="same"),
    ]
    f, cx, _, _ = extended_paper_checks([p, r], claims, decisions)
    assert not f and cx[0]["status"] == "passed"
    decisions[0]["answer"] = "best"
    f, _, _, _ = extended_paper_checks([p, r], claims, decisions)
    assert (
        f[0]["observed"]["artifact"] == 1
        and f[0]["evidence_status"] == "verified_artifact_discrepancy"
    )


def test_narrative_counts_allow_alternative_populations():
    a = artifact(
        "p",
        "paper.md",
        "documentation",
        "The study contains 100 participants with 70 training participants and 20 test participants.",
    )
    f, c, _, _ = extended_paper_checks([a], [], [])
    assert f[0]["evidence_status"] == "supported_concern" and f[0]["alternatives"]


def test_adaptive_question_cannot_invent_a_source_and_changes_interpretation():
    a = artifact(
        "p", "paper.md", "documentation", "Evaluation concerns new individuals in the study."
    )
    payload = dict(
        tool="ask_question",
        question=dict(
            artifact_id="p",
            quote="Evaluation concerns new individuals in the study.",
            title="Does this interpretation apply?",
            why="The evaluation population changes interpretation.",
            purpose="interpretation",
            finding_ids=["f"],
        ),
    )
    proposal = InvestigationProposal.model_validate(payload)
    f = [dict(id="f", evidence_status="supported_concern")]
    q = grounded_question(proposal, [a], f, [])
    assert q
    q["answer"] = "alternative"
    apply_interpretations(f, [q])
    assert f[0]["evidence_status"] == "inconclusive"
    payload["question"]["quote"] = "A completely invented paper claim."
    assert grounded_question(InvestigationProposal.model_validate(payload), [a], f, []) is None


@pytest.mark.asyncio
async def test_adaptive_tool_performs_a_real_check():
    a = artifact("a", "train.csv", "data", "x,y\n1,0\n2,1\n")
    b = artifact("b", "test.csv", "data", "x,y\n2,1\n3,0\n")

    class Provider:
        questions = []

        async def next_action(self, *args):
            return InvestigationProposal(tool="run_check", check="partitions")

    findings, checks, questions, history = [], [], [], []
    await investigate(
        Provider(), [a, b], [], findings, checks, questions, [], history, lambda a: None
    )
    assert checks and history and history[0]["result"]["checks"]


def test_unverified_ocr_cannot_verify_a_discrepancy():
    passage = dict(
        id="p:1",
        artifact_id="p",
        path="paper.pdf",
        page=1,
        kind="ocr_passage",
        text="Accuracy: 91.2%.",
    )
    a = dict(id="p", path="paper.pdf", parsed=dict(anchors=[passage]))
    q = verification_questions([a], [])
    f = [dict(evidence_status="verified_artifact_discrepancy", impact="high", evidence=[passage])]
    gate_ocr(f, [], q)
    assert f[0]["evidence_status"] == "inconclusive"
    q[0]["answer"] = "confirmed"
    f[0]["evidence_status"] = "verified_artifact_discrepancy"
    gate_ocr(f, [], q)
    assert f[0]["evidence_status"] == "verified_artifact_discrepancy"


@pytest.mark.asyncio
async def test_recovery_reuses_only_valid_measured_output_and_cleans_up(monkeypatch):
    initialize()
    csv = b"x,y\n1,0\n2,1\n"
    digest = hashlib.sha256(csv).hexdigest()
    with Session() as db:
        case = Case(owner="recovery-acceptance", status="checking", result={"_elapsed_seconds": 12})
        db.add(case)
        db.commit()
        cid = case.id
        key = cid + "/data"
        storage.put(key, csv)
        data = Artifact(
            case_id=cid, path="data.csv", kind="data", size=len(csv), sha256=digest, storage_key=key
        )
        db.add(data)
        db.commit()
        job = Job(case_id=cid, state="running", revision=0)
        db.add(job)
        run = Execution(
            case_id=cid,
            status="running",
            sandbox_id="cntr_unit",
            fingerprint="test",
            manifest=dict(runner="openai", dataset_id=data.id, worker_sha256="worker"),
        )
        db.add(run)
        db.commit()
        rid = run.id
        jid = job.id
    killed = []

    async def recover(_):
        return dict(metrics={"accuracy": 0.5}, worker_sha256="worker", dataset_sha256=digest)

    async def destroy(id):
        killed.append(id)

    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-no-network")
    monkeypatch.setattr("claimbreaker.recovery.recover_openai", recover)
    monkeypatch.setattr("claimbreaker.openai_sandbox.destroy", destroy)
    await reconcile()
    with Session() as db:
        assert db.get(Execution, rid).status == "completed"
        assert db.get(Job, jid).state == "queued"
        assert db.get(Case, cid).result["_resume_count"] == 1
        db.get(Job, jid).state = "cancelled"
        db.get(Case, cid).status = "cancelled"
        db.commit()
    assert killed == ["cntr_unit"]


def test_original_run_comparison_requires_scientific_context_and_excludes_corrections():
    from claimbreaker.run_checks import paper_execution_checks

    claim = extract_claims([artifact("p", "paper.md", "documentation", "Accuracy: 90.0%.")])[0]
    run = {
        "id": "run-1",
        "status": "completed",
        "manifest": {"classification": "original_execution", "variant": "baseline"},
        "output": {"metrics": {"accuracy": 0.8}},
    }
    f, c, q = paper_execution_checks([claim], [run], [])
    assert not f and c[0]["status"] == "inconclusive"
    f, c, _ = paper_execution_checks(
        [claim], [run], [{"question_id": q[0]["id"], "answer": "same"}]
    )
    assert (
        f[0]["evidence_status"] == "reproduction_difference" and f[0]["observed"]["artifact"] == 0.8
    )
    run["manifest"]["classification"] = "corrected_protocol"
    assert paper_execution_checks([claim], [run], []) == ([], [], [])


def test_figure_pdfs_do_not_become_primary_papers():
    from claimbreaker.ingest import classify

    assert classify("docs/img/logo.pdf") == "figure"
    assert classify("paper.pdf") == "paper"


def test_private_pdf_page_endpoint_returns_real_geometry():
    from fastapi.testclient import TestClient
    from claimbreaker.app import app

    with TestClient(app) as client:
        case = client.post("/api/v1/cases", json={"provider": "deterministic"}).json()
        client.post("/api/v1/cases/" + case["id"] + "/sample/paper")
        import time

        for _ in range(300):
            case = client.get("/api/v1/cases/" + case["id"]).json()
            if case["status"] in {"awaiting_input", "partially_complete", "review_ready", "failed"}:
                break
            time.sleep(0.1)
        paper = next(a for a in case["artifacts"] if a["path"] == "paper.pdf")
        url = f"/api/v1/cases/{case['id']}/artifacts/{paper['id']}/pages/1"
        page = client.get(url, params={"quote": "Test accuracy"})
        assert page.status_code == 200, page.text
        data = page.json()
        assert data["image"].startswith("data:image/png;base64,") and data["boxes"]
        with TestClient(app) as stranger:
            assert stranger.get(url).status_code == 404


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows job objects")
def test_windows_parser_memory_limit_and_kill_on_close():
    import subprocess, sys
    from claimbreaker.windows_limits import parser_job

    code = 'import sys\nsys.stdin.read(1)\ntry:\n x=bytearray(256*1024**2)\n print("unexpected allocation")\nexcept MemoryError:\n print("allocation blocked")'
    process = subprocess.Popen(
        [sys._base_executable, "-I", "-c", code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    job = parser_job(process.pid, 64 * 1024**2)
    try:
        out, _ = process.communicate(b"1", timeout=10)
        assert process.returncode == 0 and b"allocation blocked" in out
    finally:
        job.close()
    process = subprocess.Popen(
        [sys._base_executable, "-I", "-c", "import time;time.sleep(60)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    started = __import__("time").monotonic()
    job = parser_job(process.pid)
    job.close()
    process.wait(timeout=5)
    assert __import__("time").monotonic() - started < 5 and process.poll() is not None


def test_preprocessing_correction_requires_a_decision_and_combines_with_time():
    from claimbreaker.research_checks import expanded_checks
    from claimbreaker.execution_planning import execution_plan

    source = """import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
data=pd.read_csv("data.csv")
X=data[["x"]]
y=data["outcome"]
scaler=StandardScaler()
X=scaler.fit_transform(X)
X_train,X_test,y_train,y_test=train_test_split(X,y,test_size=.25,random_state=42)
model=LogisticRegression(max_iter=200)
model.fit(X_train,y_train)
print(accuracy_score(y_test,model.predict(X_test)))
"""
    inventory = [
        artifact("code", "train.py", "code", source),
        artifact(
            "data",
            "data.csv",
            "data",
            "x,outcome,date\n1,0,2020-01-01\n2,1,2020-01-02\n3,0,2020-01-03\n4,1,2020-01-04\n",
        ),
    ]
    _, _, questions = expanded_checks(inventory, [])
    temporal = next(q for q in questions if q["id"].startswith("temporal"))
    preprocessing = next(q for q in questions if q["id"].startswith("preprocessing"))
    decisions = [dict(question_id=temporal["id"], answer="future")]
    plans, reason = execution_plan(inventory, decisions)
    assert len(plans) == 1 and "explicit" in reason
    decisions.append(dict(question_id=preprocessing["id"], answer="training_only"))
    plans, reason = execution_plan(inventory, decisions)
    assert (
        len(plans) == 2
        and plans[1]["variant"] == "temporal"
        and plans[1]["preprocessing_policy"] == "training_only"
    )


def test_graph_preserves_execution_evidence_for_scientific_questions():
    from claimbreaker.checks import graph_for
    from claimbreaker.run_checks import paper_execution_checks

    a = artifact("p", "paper.md", "documentation", "Accuracy: 90.0%.")
    claims = extract_claims([a])
    run = dict(
        id="run",
        status="completed",
        manifest=dict(classification="original_execution", variant="baseline"),
        output=dict(metrics=dict(accuracy=0.8)),
    )
    f, c, q = paper_execution_checks(claims, [run], [])
    graph = graph_for([a], claims, f, [run], q, c)
    assert any(e["source"] == "run" and e["target"] == q[0]["id"] for e in graph["edges"])


@pytest.mark.asyncio
async def test_provider_prospective_budget_never_sends_an_over_budget_request(monkeypatch):
    from claimbreaker.providers import ModelProvider
    from claimbreaker.schemas import ClaimBatch

    p = ModelProvider("openai")
    p.input_chars = 319990

    async def forbidden(*args, **kwargs):
        raise AssertionError("Over-budget request was sent")

    monkeypatch.setattr(p, "_request", forbidden)
    assert await p.generate("x" * 20, ClaimBatch) is None
    assert p.input_chars == 319990 and p.steps == 0 and p.warnings


def test_mutations_allow_proxy_port_difference():
    from fastapi.testclient import TestClient
    from claimbreaker.app import app

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/cases", json={}, headers={"origin": "http://testserver:9999"}
        )
        assert response.status_code == 201
        assert (
            client.post(
                "/api/v1/cases", json={}, headers={"origin": "http://testserver"}
            ).status_code
            == 201
        )
