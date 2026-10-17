import asyncio
from datetime import timedelta
from types import SimpleNamespace
import pytest
from claimbreaker.db import initialize, Session, Case, Artifact, Event, utcnow, emit
from claimbreaker.engine import RUNNING, cancel_analysis, expire_cases
from claimbreaker.app import events
from claimbreaker.parser_process import parse_bounded
from claimbreaker import storage


@pytest.mark.asyncio
async def test_cancel_stops_actual_analysis_task():
    task = asyncio.create_task(asyncio.sleep(100))
    RUNNING["cancel-unit"] = task
    await cancel_analysis("cancel-unit")
    assert task.cancelled()
    RUNNING.pop("cancel-unit", None)


@pytest.mark.asyncio
async def test_expiry_removes_metadata_and_source_bytes():
    initialize()
    with Session() as db:
        c = Case(owner="retention-test", created_at=utcnow() - timedelta(days=8))
        db.add(c)
        db.commit()
        id = c.id
        key = id + "/source"
        storage.put(key, b"old source")
        db.add(
            Artifact(
                case_id=id,
                path="README.md",
                kind="documentation",
                size=10,
                sha256="a" * 64,
                storage_key=key,
            )
        )
        db.commit()
    await expire_cases()
    with Session() as db:
        assert db.get(Case, id) is None
    assert not storage.local_path(key).exists()


@pytest.mark.asyncio
async def test_sse_replays_only_events_after_cursor():
    initialize()
    with Session() as db:
        c = Case(owner="sse-owner")
        db.add(c)
        db.commit()
        id = c.id
        first = emit(db, id, "inspecting", "First").id
        last = emit(db, id, "checking", "Second").id

    class Request:
        session = {"owner": "sse-owner"}
        headers = {"last-event-id": str(first)}

        async def is_disconnected(self):
            return False

    response = await events(id, Request())
    stream = response.body_iterator
    item = await anext(stream)
    assert f"id: {last}" in item and '"message": "Second"' in item
    await stream.aclose()


@pytest.mark.asyncio
async def test_parser_treats_source_as_text_and_detects_lfs():
    a = SimpleNamespace(id="test", path="train.py", kind="code")
    parsed = await parse_bounded(a, b"raise RuntimeError('This must not execute')")
    assert "raise RuntimeError" in parsed["text"]
    a.path = "data.csv"
    parsed = await parse_bounded(a, b"version https://git-lfs.github.com/spec/v1\noid sha256:abc")
    assert parsed["unavailable"] and "LFS" in parsed["warnings"][0]
