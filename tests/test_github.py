import io
import zipfile
import httpx
import pytest
from claimbreaker.config import settings
from claimbreaker.ingest import fetch_github, IntakeError


@pytest.mark.asyncio
async def test_snapshot_pins_sha_and_does_not_leak_token(monkeypatch):
    monkeypatch.setattr(settings(), "offline", False)
    monkeypatch.setenv("GITHUB_TOKEN", "mock-token")
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr("repo-sha/README.md", "# Test research source")
    sha = "a" * 40
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.host == "codeload.github.com":
            assert "authorization" not in request.headers
            assert sha in request.url.path
            return httpx.Response(200, content=data.getvalue())
        assert request.headers["authorization"] == "Bearer mock-token"
        return httpx.Response(
            200,
            json={"default_branch": "main"}
            if not "/commits/" in request.url.path
            else {"sha": sha},
        )

    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    files, ignored, source = await fetch_github("https://github.com/team/repo")
    assert source["commit"] == sha and files[0][0] == "README.md" and len(seen) == 3


@pytest.mark.asyncio
async def test_github_rate_limit_is_actionable(monkeypatch):
    monkeypatch.setattr(settings(), "offline", False)
    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(429)), **kw),
    )
    with pytest.raises(IntakeError, match="rate limit"):
        await fetch_github("https://github.com/team/repo")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://github.com.evil.example/a/b",
        "https://user:password@github.com/a/b",
        "http://github.com/a/b",
        "https://169.254.169.254/a/b",
        "https://github.com:444/a/b",
    ],
)
async def test_ssrf_and_credential_urls_rejected(url, monkeypatch):
    monkeypatch.setattr(settings(), "offline", False)
    with pytest.raises(IntakeError):
        await fetch_github(url)
