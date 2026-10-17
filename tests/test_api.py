import time
from fastapi.testclient import TestClient
from claimbreaker.app import app


def wait_case(client, id):
    for _ in range(450):
        c = client.get(f"/api/v1/cases/{id}").json()
        if c["status"] in {"review_ready", "partially_complete", "awaiting_input", "failed"}:
            return c
        time.sleep(0.1)
    raise AssertionError("Investigation did not settle")


def test_complete_paper_case_and_private_session():
    with TestClient(app) as client:
        c = client.post("/api/v1/cases", json={"provider": "deterministic"}).json()
        id = c["id"]
        response = client.post(f"/api/v1/cases/{id}/sample/paper")
        assert response.status_code == 200
        c = wait_case(client, id)
        assert c["status"] != "failed", c
        assert c["result"]["findings"]
        assert any(f["kind"] == "paper_repository" for f in c["result"]["findings"])
        assert (
            client.post(
                f"/api/v1/cases/{id}/decisions",
                json={"question_id": "repository-version", "answer": "same"},
            ).status_code
            == 200
        )
        c = wait_case(client, id)
        assert any(
            f["evidence_status"] == "verified_artifact_discrepancy" for f in c["result"]["findings"]
        )
        f = c["result"]["findings"][0]
        assert (
            client.post(
                f"/api/v1/cases/{id}/findings/{f['id']}/review",
                json={
                    "status": "accepted",
                    "note": "Confirmed the synthetic snapshot correspondence.",
                },
            ).status_code
            == 200
        )
        assert client.get(f"/api/v1/cases/{id}/exports/pdf").content.startswith(b"%PDF")
        assert client.get(f"/api/v1/cases/{id}/exports/zip").content.startswith(b"PK")
        with TestClient(app) as stranger:
            assert stranger.get(f"/api/v1/cases/{id}").status_code == 404
        assert client.delete(f"/api/v1/cases/{id}").status_code == 200
        assert client.get(f"/api/v1/cases/{id}").status_code == 404


def test_clean_control_not_condemned():
    with TestClient(app) as client:
        c = client.post("/api/v1/cases", json={"provider": "deterministic"}).json()
        id = c["id"]
        client.post(f"/api/v1/cases/{id}/sample/clean")
        c = wait_case(client, id)
        assert c["status"] != "failed", c
        assert not c["result"]["findings"], c["result"]["findings"]
        assert any(check["status"] == "passed" for check in c["result"]["checks"])


def test_bad_source_and_unknown_decision():
    with TestClient(app) as client:
        c = client.post("/api/v1/cases", json={"provider": "deterministic"}).json()
        id = c["id"]
        assert client.post(f"/api/v1/cases/{id}/start").status_code == 400
        assert (
            client.post(
                f"/api/v1/cases/{id}/artifacts", files={"file": ("evil.zip", b"bad")}
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/api/v1/cases/{id}/sources/github", json={"url": "http://169.254.169.254/latest"}
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/api/v1/cases/{id}/decisions", json={"question_id": "made-up", "answer": "yes"}
            ).status_code
            == 400
        )


def test_failed_runner_is_visible_and_leaves_partial_case(monkeypatch):
    class GroundedProvider:
        def __init__(self, *args):
            self.used = "unit-test-provider"
            self.warnings = []

        async def extract_claims(self, *args):
            return None

        async def next_action(self, *args):
            return None

    async def capability():
        return {"available": True, "provider": "test-adapter", "reason": "Test failure path only"}

    async def failed_run(*args):
        raise RuntimeError("Simulated runner unavailable")

    monkeypatch.setattr("claimbreaker.engine.ModelProvider", GroundedProvider)
    monkeypatch.setattr("claimbreaker.engine.runner_status", capability)
    monkeypatch.setattr("claimbreaker.engine.run_isolated", failed_run)
    with TestClient(app) as client:
        case = client.post("/api/v1/cases", json={}).json()
        client.post(f"/api/v1/cases/{case['id']}/sample/clean")
        completed = wait_case(client, case["id"])
        assert completed["status"] == "partially_complete"
        assert completed["result"]["executions"][0]["status"] == "failed"
        assert any(
            c["name"] == "Supported CPU evaluation" and c["status"] == "inconclusive"
            for c in completed["result"]["checks"]
        )
