import asyncio
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from claimbreaker.runner_service import app
from claimbreaker.config import settings


def test_broker_requires_private_token_and_validated_spec(monkeypatch):
    cfg = settings()
    for key in ("runner", "runner_url", "offline"):
        monkeypatch.setattr(cfg, key, getattr(cfg, key))
    monkeypatch.setattr(cfg, "runner_token", "unit-test-private-token-32-characters-long")

    async def capability():
        return {
            "available": False,
            "provider": "docker",
            "reason": "unit test: engine is not launched",
        }

    monkeypatch.setattr("claimbreaker.runner_service.runner_status", capability)
    with TestClient(app) as client:
        assert client.get("/capabilities").status_code == 401
        headers = {"Authorization": "Bearer " + cfg.runner_token}
        assert client.get("/capabilities", headers=headers).status_code == 200
        payload = {
            "case_id": str(uuid4()),
            "execution_id": str(uuid4()),
            "csv": "x,y\n1,2",
            "spec": {
                "dataset_id": "d",
                "code_id": "c",
                "target": "y",
                "features": ["x"],
                "estimator": "arbitrary_shell",
                "variant": "baseline",
            },
        }
        assert client.post("/executions", headers=headers, json=payload).status_code == 422


def test_broker_cancels_real_pending_task(monkeypatch):
    cfg = settings()
    for key in ("runner", "runner_url", "offline"):
        monkeypatch.setattr(cfg, key, getattr(cfg, key))
    monkeypatch.setattr(cfg, "runner_token", "unit-test-private-token-32-characters-long")
    case_id = str(uuid4())

    async def fake_run(*args):
        await asyncio.sleep(100)

    monkeypatch.setattr("claimbreaker.runner_service.run_isolated", fake_run)

    async def no_terminate(*args):
        pass

    monkeypatch.setattr("claimbreaker.runner_service.terminate", no_terminate)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer " + cfg.runner_token}
        from claimbreaker.runner_service import TASKS

        async def create():
            TASKS[case_id] = asyncio.create_task(asyncio.sleep(100))

        client.portal.call(create)
        assert client.delete("/executions/" + case_id, headers=headers).json()["cancelled"]
        assert TASKS[case_id].cancelled() or TASKS[case_id].cancelling()
        TASKS.pop(case_id, None)


def test_cancellation_before_post_prevents_late_execution(monkeypatch):
    cfg = settings()
    for key in ("runner", "runner_url", "offline"):
        monkeypatch.setattr(cfg, key, getattr(cfg, key))
    monkeypatch.setattr(cfg, "runner_token", "unit-test-private-token-32-characters-long")

    async def forbidden(*args):
        raise AssertionError("Cancelled run must not start")

    monkeypatch.setattr("claimbreaker.runner_service.run_isolated", forbidden)
    case_id = str(uuid4())
    execution_id = str(uuid4())
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer " + cfg.runner_token}
        assert (
            client.delete(
                "/executions/" + case_id, params={"execution_id": execution_id}, headers=headers
            ).status_code
            == 200
        )
        payload = {
            "case_id": case_id,
            "execution_id": execution_id,
            "csv": "x,y\n1,0\n2,1\n",
            "spec": {
                "dataset_id": "d",
                "code_id": "c",
                "target": "y",
                "features": ["x"],
                "estimator": "LogisticRegression",
                "variant": "baseline",
            },
        }
        assert client.post("/executions", headers=headers, json=payload).status_code == 409
