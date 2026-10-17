import json
import httpx
import pytest
from claimbreaker.config import settings
from claimbreaker.providers import ModelProvider, redact, ollama_status
from claimbreaker.schemas import ClaimBatch


@pytest.mark.asyncio
async def test_provider_repairs_invalid_schema_then_succeeds(monkeypatch):
    monkeypatch.setattr(settings(), "offline", False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-real-secret")
    calls = []

    async def request(self, provider, prompt, schema):
        calls.append(provider)
        return (
            {"claims": [{"artifact_id": "x", "quote": "short", "type": "invented"}]}
            if len(calls) == 1
            else {"claims": []}
        )

    monkeypatch.setattr(ModelProvider, "_request", request)
    provider = ModelProvider("openai")
    assert (await provider.generate("Extract evidence", ClaimBatch)).claims == []
    assert provider.used == "openai" and len(calls) == 2


@pytest.mark.asyncio
async def test_hosted_outage_falls_back_only_to_reachable_ollama(monkeypatch):
    monkeypatch.setattr(settings(), "offline", False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-real-secret")

    async def available():
        return {"available": True}

    monkeypatch.setattr("claimbreaker.providers.ollama_status", available)
    calls = []

    async def request(self, provider, prompt, schema):
        calls.append(provider)
        if provider == "openai":
            raise httpx.ConnectError("simulated outage")
        return {"claims": []}

    monkeypatch.setattr(ModelProvider, "_request", request)
    provider = ModelProvider("auto")
    assert await provider.generate("Extract", ClaimBatch)
    assert provider.used == "ollama" and calls == ["openai", "openai", "ollama"]
    assert any("openai" in w for w in provider.warnings)


@pytest.mark.asyncio
async def test_offline_provider_never_calls_hosted(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-real-secret")
    monkeypatch.setattr(settings(), "offline", True)

    async def unavailable():
        return {"available": False}

    monkeypatch.setattr("claimbreaker.providers.ollama_status", unavailable)

    async def forbidden(*args):
        raise AssertionError("No network model call should occur")

    monkeypatch.setattr(ModelProvider, "_request", forbidden)
    p = ModelProvider("auto")
    assert await p.generate("Extract", ClaimBatch) is None
    assert p.used == "deterministic"


@pytest.mark.asyncio
async def test_responses_api_shape_and_secret_redaction(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "mock-private-key")
    seen = []

    def transport(request):
        body = json.loads(request.content)
        seen.append(body)
        assert body["store"] is False
        assert body["text"]["format"]["strict"] is True
        return httpx.Response(
            200, json={"output": [{"content": [{"type": "output_text", "text": '{"claims":[]}'}]}]}
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs),
    )
    result = await ModelProvider("openai")._request(
        "openai", "source", ClaimBatch.model_json_schema()
    )
    assert result == {"claims": []} and len(seen) == 1
    assert "sensitive-value" not in redact("api_key=sensitive-value")


@pytest.mark.asyncio
async def test_unavailable_or_wrong_local_model(monkeypatch):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"models": [{"name": "different-model:8b"}]})
    )
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs)
    )
    assert not (await ollama_status())["available"]
