import pytest


@pytest.mark.parametrize("configured", ["", "https://old-service.example", "unused-legacy-value"])
def test_proxy_origin_never_blocks_mutations_and_cases_remain_private(monkeypatch, configured):
    from fastapi.testclient import TestClient
    from claimbreaker.app import app, settings

    monkeypatch.setattr(settings(), "public_origin", configured)
    with TestClient(app, base_url="http://internal-service:5173") as owner:
        response = owner.post(
            "/api/v1/cases", json={}, headers={"origin": "https://new-public-service.example"}
        )
        assert response.status_code == 201
        assert "httponly" in response.headers["set-cookie"].lower()
        assert "samesite=strict" in response.headers["set-cookie"].lower()
        case_id = response.json()["id"]
        assert owner.get(f"/api/v1/cases/{case_id}").status_code == 200
        with TestClient(app, base_url="http://internal-service:5173") as stranger:
            assert stranger.get(f"/api/v1/cases/{case_id}").status_code == 404
            assert stranger.delete(f"/api/v1/cases/{case_id}").status_code == 404
        assert (
            owner.delete(
                f"/api/v1/cases/{case_id}", headers={"origin": "https://new-public-service.example"}
            ).status_code
            == 200
        )
