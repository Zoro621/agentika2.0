import pytest

from claimbreaker.origins import mutation_origin_allowed, normalize_origin


@pytest.mark.parametrize(
    "origin,allowed",
    [
        ("https://research.example", True),
        ("https://research.example:443", True),
        ("http://research.example", False),
        ("https://research.example:5173", False),
        ("https://evil.example", False),
        ("https://research.example.evil.example", False),
        ("null", False),
        ("https://research.example@evil.example", False),
    ],
)
def test_public_origin_behind_internal_http_proxy(origin, allowed):
    assert (
        mutation_origin_allowed(origin, "http://internal-service:5173/", "https://research.example")
        is allowed
    )


def test_local_origin_still_requires_matching_port():
    assert mutation_origin_allowed("http://localhost:5173", "http://localhost:5173/")
    assert not mutation_origin_allowed("http://localhost:8000", "http://localhost:5173/")


@pytest.mark.parametrize(
    "value", ["*", "null", "https://site.example/path", "https://site.example:bad"]
)
def test_invalid_public_origin_rejected(value):
    from claimbreaker.config import Settings

    with pytest.raises(ValueError):
        Settings(public_origin=value)


def test_normalization_preserves_ipv6_and_port():
    assert normalize_origin("http://[::1]:5173/") == "http://[::1]:5173"


def test_mutation_uses_configured_public_origin(monkeypatch):
    from fastapi.testclient import TestClient
    from claimbreaker.app import app, settings

    monkeypatch.setattr(settings(), "public_origin", "https://research.example")
    with TestClient(app, base_url="http://internal-service:5173") as client:
        assert (
            client.post(
                "/api/v1/cases", json={}, headers={"origin": "https://research.example"}
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/v1/cases", json={}, headers={"origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/cases", json={}, headers={"origin": "http://internal-service:5173"}
            ).status_code
            == 403
        )
