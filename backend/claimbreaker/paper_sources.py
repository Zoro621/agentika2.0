"""A fixed-host, bounded paper retriever; never accepts arbitrary agent URLs."""

import re
from urllib.parse import urlparse
import httpx
from .config import settings

HOSTS = {"arxiv.org", "export.arxiv.org", "www.theoj.org", "joss.theoj.org"}


def paper_candidates(files):
    candidates = {}
    for path, data in files:
        if not path.lower().endswith((".md", ".rst", ".txt")):
            continue
        text = data[:100000].decode(errors="replace")
        for match in re.finditer(
            r"https?://(?:arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)|(?:joss\.theoj\.org/papers/|doi\.org/)?10\.21105/joss\.(\d+))",
            text,
        ):
            if match.group(1):
                identifier = match.group(1).removesuffix(".pdf")
                url = "https://arxiv.org/pdf/" + identifier
                key = "arxiv-" + identifier
            else:
                identifier = match.group(2)
                url = f"https://www.theoj.org/joss-papers/joss.{identifier}/10.21105.joss.{identifier}.pdf"
                key = "joss-" + identifier
            candidates[url] = {"url": url, "path": f"linked-papers/{key}.pdf", "linked_from": path}
    return list(candidates.values())[:2]


async def fetch_linked_papers(files):
    if settings().offline:
        return [], []
    acquired, records = [], []
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        for candidate in paper_candidates(files):
            record = {**candidate, "status": "unavailable"}
            try:
                url = candidate["url"]
                for _ in range(3):
                    parsed = urlparse(url)
                    if (
                        parsed.scheme != "https"
                        or parsed.hostname not in HOSTS
                        or parsed.username
                        or parsed.password
                        or parsed.port
                    ):
                        raise ValueError("Paper destination is outside approved publishers")
                    async with client.stream(
                        "GET", url, headers={"User-Agent": "ClaimBreaker/0.1"}
                    ) as response:
                        if response.is_redirect:
                            from urllib.parse import urljoin

                            url = urljoin(url, response.headers["location"])
                            continue
                        response.raise_for_status()
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > 25 * 1024**2:
                                raise ValueError("Linked paper exceeds the 25 MB limit")
                        if not data.startswith(b"%PDF"):
                            raise ValueError("Publisher did not return a PDF")
                        import hashlib

                        digest = hashlib.sha256(data).hexdigest()
                        if not any(
                            path.lower().endswith(".pdf")
                            and hashlib.sha256(content).hexdigest() == digest
                            for path, content in files
                        ):
                            acquired.append((candidate["path"], bytes(data)))
                        record.update(status="acquired", resolved_url=url)
                        break
                if record["status"] != "acquired":
                    record["reason"] = "Publisher redirect limit reached"
            except Exception as exc:
                record["reason"] = (
                    f"Paper acquisition unavailable ({type(exc).__name__}); upload its PDF to inspect it."
                )
            records.append(record)
    return acquired, records
