import httpx
import pytest
from claimbreaker.config import settings
from claimbreaker.paper_sources import paper_candidates, fetch_linked_papers


def test_only_recognized_paper_sources_become_fetch_candidates():
    candidates = paper_candidates(
        [
            (
                "README.md",
                b"Paper https://arxiv.org/pdf/2601.12345v2.pdf Also https://joss.theoj.org/papers/10.21105/joss.00638 and https://169.254.169.254/latest",
            )
        ]
    )
    assert len(candidates) == 2 and candidates[0]["url"] == "https://arxiv.org/pdf/2601.12345v2"
    assert all("169.254" not in c["url"] for c in candidates)


@pytest.mark.asyncio
async def test_publisher_redirect_cannot_reach_private_network(monkeypatch):
    monkeypatch.setattr(settings(), "offline", False)
    real = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    files, records = await fetch_linked_papers([("README.md", b"https://arxiv.org/abs/2601.12345")])
    assert not files and records[0]["status"] == "unavailable" and len(requests) == 1


@pytest.mark.asyncio
async def test_offline_mode_does_not_fetch_linked_paper(monkeypatch):
    monkeypatch.setattr(settings(), "offline", True)

    def forbidden(**kw):
        raise AssertionError("External request in offline mode")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    assert await fetch_linked_papers([("README.md", b"https://arxiv.org/abs/2601.12345")]) == (
        [],
        [],
    )
