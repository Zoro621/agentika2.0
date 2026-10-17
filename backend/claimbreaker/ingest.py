"""Bounded, non-executing source acquisition."""

import hashlib
import io
import os
import re
import stat
import zipfile
from pathlib import PurePosixPath
from urllib.parse import urlparse, quote
import httpx
from .config import settings
from .db import Artifact
from . import storage

IGNORED = {
    ".git",
    ".aws",
    ".ssh",
    "credentials",
    "secrets",
    "tokens",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".ipynb_checkpoints",
    "dist",
    "build",
}
ALLOWED = {
    ".pdf",
    ".py",
    ".ipynb",
    ".csv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".md",
    ".txt",
    ".r",
    ".rst",
    ".tex",
    ".tsv",
}
SECRET = re.compile(
    r"(^\.env($|\.)|\.pem$|\.key$|credentials|id_rsa|id_ed25519|^\.(?:netrc|npmrc|pypirc)$|^(?:tokens?|api[_-]?keys?)[.\-_]|secrets?\.)",
    re.I,
)


class IntakeError(ValueError):
    pass


def classify(path):
    p = PurePosixPath(path)
    ext, name = p.suffix.lower(), p.name.lower()
    if ext == ".pdf":
        return (
            "figure"
            if any(
                part.lower() in {"figures", "plots", "images", "img", "icons"} for part in p.parts
            )
            or re.match(r"(?:fig(?:ure)?|plot)[_\d.-]", name)
            or name.startswith(("logo.", "icon."))
            else "paper"
        )
    if ext in {".py", ".ipynb", ".r"}:
        return "code"
    if ext in {".csv", ".tsv"}:
        return (
            "results"
            if any(x in path.lower() for x in ("result", "metric", "prediction", "score"))
            else "data"
        )
    if ext in {".yaml", ".yml", ".toml"} or "config" in name or name == "requirements.txt":
        return "configuration"
    if ext in {".json", ".jsonl"}:
        return (
            "results"
            if any(x in path.lower() for x in ("result", "metric", "score", "evaluation"))
            else "data"
        )
    return "documentation"


def normalized_path(name):
    name = name.replace("\\", "/")
    p = PurePosixPath(name)
    if (
        p.is_absolute()
        or ".." in p.parts
        or re.match(r"^[a-zA-Z]:", name)
        or any(ord(c) < 32 for c in name)
        or ":" in name
    ):
        raise IntakeError("Archive contains an unsafe path")
    return str(p)


def unpack(filename, content):
    cfg = settings()
    if len(content) > cfg.max_upload:
        raise IntakeError("Upload exceeds 50 MB")
    if filename.lower().endswith(".zip"):
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise IntakeError("This file is not a valid ZIP archive") from exc
        entries = archive.infolist()
        if len(entries) > cfg.max_entries:
            raise IntakeError("Archive contains too many entries (limit: 2,000)")
        total, seen, selected, ignored = 0, set(), [], []
        for info in entries:
            path = normalized_path(info.filename)
            folded = path.casefold()
            if folded in seen:
                raise IntakeError("Archive contains duplicate normalized paths")
            seen.add(folded)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise IntakeError("Links and special files are not accepted")
            if info.flag_bits & 1:
                raise IntakeError("Encrypted archives are not supported")
            if info.is_dir():
                continue
            total += info.file_size
            if total > cfg.max_extracted or info.file_size > 100 * 1024 * 1024:
                raise IntakeError("Archive extraction limit exceeded")
            if info.file_size > 1024 * 1024 and info.file_size / max(info.compress_size, 1) > 200:
                raise IntakeError("Suspicious archive compression ratio")
            p = PurePosixPath(path)
            if (
                any(x in IGNORED for x in p.parts)
                or SECRET.search(p.name)
                or p.suffix.lower() not in ALLOWED
            ):
                ignored.append(path)
                continue
            if p.suffix.lower() == ".pdf" and info.file_size > 25 * 1024 * 1024:
                raise IntakeError("PDF exceeds 25 MB")
            if (
                p.suffix.lower() not in {".pdf", ".csv", ".tsv"}
                and info.file_size > 5 * 1024 * 1024
            ):
                ignored.append(path)
                continue
            try:
                data = archive.read(info)
            except (zipfile.BadZipFile, RuntimeError) as exc:
                raise IntakeError("Archive entry is damaged or cannot be decoded") from exc
            if len(data) != info.file_size:
                raise IntakeError("Truncated archive entry")
            selected.append((path, data))
        return selected, ignored
    name = PurePosixPath(normalized_path(filename)).name
    if not name.lower().endswith(".pdf"):
        raise IntakeError("Drop a ZIP research project or a PDF paper")
    if len(content) > 25 * 1024 * 1024:
        raise IntakeError("PDF exceeds 25 MB")
    return [(name, content)], []


def import_files(db, case_id, files):
    from sqlalchemy import select

    prior = list(db.scalars(select(Artifact).where(Artifact.case_id == case_id)))
    existing = {a.path.casefold() for a in prior}
    if len(existing) + len(files) > settings().max_entries:
        raise IntakeError("Case artifact limit exceeded")
    if sum(a.size for a in prior) + sum(len(data) for _, data in files) > settings().max_extracted:
        raise IntakeError("Combined case sources exceed the 250 MB extracted-content limit")
    for path, data in files:
        if path.casefold() in existing:
            raise IntakeError(
                f"An artifact named {path} already exists; start a new case or rename the file"
            )
        existing.add(path.casefold())
    created = []
    for path, data in files:
        digest = hashlib.sha256(data).hexdigest()
        key = f"{case_id}/{digest}"
        storage.put(key, data)
        item = Artifact(
            case_id=case_id,
            path=path,
            kind=classify(path),
            size=len(data),
            sha256=digest,
            storage_key=key,
        )
        db.add(item)
        created.append(item)
    db.commit()
    return created


async def fetch_github(url, ref=None, discover_papers=True):
    if settings().offline:
        raise IntakeError("GitHub acquisition is disabled in offline mode; upload a repository ZIP")
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as exc:
        raise IntakeError("Invalid repository URL") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username
        or parsed.password
        or parsed.port
    ):
        raise IntakeError("Use an HTTPS github.com repository URL")
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2 or not all(re.fullmatch(r"[\w.-]+", p) for p in parts[:2]):
        raise IntakeError("Invalid repository URL")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if len(parts) >= 4 and parts[2] in {"tree", "commit"} and not ref:
        ref = "/".join(parts[3:])
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ClaimBreaker/0.1"}
    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        meta = await client.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers)
        _github_ok(meta)
        if meta.json().get("private"):
            raise IntakeError(
                "Only public GitHub acquisition is supported; upload a private repository ZIP instead"
            )
        if not ref:
            ref = meta.json()["default_branch"]
        response = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/commits/{quote(ref, safe='')}",
            headers=headers,
        )
        _github_ok(response)
        sha = response.json()["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise IntakeError("GitHub returned an invalid commit")
        # Direct codeload URL avoids sending API credentials to redirect destinations.
        async with client.stream(
            "GET", f"https://codeload.github.com/{owner}/{repo}/zip/{sha}"
        ) as archive:
            archive.raise_for_status()
            data = bytearray()
            async for chunk in archive.aiter_bytes():
                data.extend(chunk)
                if len(data) > settings().max_upload:
                    raise IntakeError(
                        "Repository archive exceeds 50 MB; upload a smaller source snapshot"
                    )
    files, ignored = unpack(f"{repo}.zip", bytes(data))
    roots = {path.split("/")[0] for path, _ in files}
    if len(roots) == 1:
        files = [(p.split("/", 1)[1] if "/" in p else p, b) for p, b in files]
    from .paper_sources import fetch_linked_papers

    papers, paper_records = await fetch_linked_papers(files) if discover_papers else ([], [])
    files += papers
    return (
        files,
        ignored,
        {
            "type": "github",
            "url": f"https://github.com/{owner}/{repo}",
            "ref": ref,
            "commit": sha,
            "sha256": hashlib.sha256(data).hexdigest(),
            "linked_papers": paper_records,
        },
    )


def _github_ok(response):
    if response.status_code in (403, 429):
        raise IntakeError(
            "GitHub rate limit or access restriction. Retry later or configure a server-side GitHub token"
        )
    if response.status_code == 404:
        raise IntakeError(
            "Repository or reference is unavailable. Use a public repository or upload a ZIP"
        )
    response.raise_for_status()
