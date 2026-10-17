from fastapi.testclient import TestClient
from claimbreaker.app import app
from claimbreaker.config import settings


def test_declared_oversize_is_rejected_before_upload_parsing():
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/cases",
            content=b"{}",
            headers={"content-type": "application/json", "content-length": str(2 * 1024**2)},
        )
        assert response.status_code == 413


def test_chunked_upload_is_bounded_before_spooling(monkeypatch):
    monkeypatch.setattr(settings(), "max_upload", 1024)
    with TestClient(app) as client:
        case = client.post("/api/v1/cases", json={}).json()

        def body():
            yield b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="large.zip"\r\nContent-Type: application/zip\r\n\r\n'
            yield b"x" * (70 * 1024)
            yield b"\r\n--boundary--\r\n"

        response = client.post(
            f"/api/v1/cases/{case['id']}/artifacts",
            content=body(),
            headers={"content-type": "multipart/form-data; boundary=boundary"},
        )
        assert response.status_code == 413, response.text
