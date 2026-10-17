"""Reconcile actual environments before bounded automatic job continuation."""

import asyncio
import hashlib
import os
import httpx
from sqlalchemy import select
from .db import Session, Case, Execution, Job, emit
from .config import settings
from . import storage


async def recover_openai(container_id):
    from .openai_sandbox import API

    async with httpx.AsyncClient(
        timeout=15, headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}
    ) as client:
        info = await client.get(f"{API}/containers/{container_id}")
        if info.status_code == 404:
            return None
        info.raise_for_status()
        if info.json().get("network_policy", {}).get("type") != "disabled":
            return None
        listing = await client.get(f"{API}/containers/{container_id}/files", params={"limit": 100})
        listing.raise_for_status()
        file = next(
            (
                f
                for f in listing.json()["data"]
                if f["path"] == "/mnt/data/claimbreaker-result.json"
            ),
            None,
        )
        if not file:
            return None
        response = await client.get(f"{API}/containers/{container_id}/files/{file['id']}/content")
        response.raise_for_status()
        if len(response.content) > 2 * 1024**2:
            return None
        value = response.json()
        if not value.get("ok"):
            return None
        result = value["result"]
        result["sandbox"] = {
            "provider": "openai",
            "container_id": container_id,
            "recovered": True,
            "memory_limit": "1g",
            "network_policy": "disabled",
            "output_file_id": file["id"],
        }
        return result


async def reconcile():
    from .db import Artifact
    from .openai_sandbox import destroy

    with Session() as db:
        for run in db.scalars(select(Execution).where(Execution.status == "running")):
            recovered = None
            try:
                if (
                    run.sandbox_id
                    and run.manifest.get("runner") == "openai"
                    and os.getenv("OPENAI_API_KEY")
                ):
                    try:
                        recovered = await recover_openai(run.sandbox_id)
                    finally:
                        await destroy(run.sandbox_id)
                    data = db.get(Artifact, run.manifest.get("dataset_id"))
                    expected = (
                        hashlib.sha256(
                            storage.get(data.storage_key).decode("utf-8-sig").encode()
                        ).hexdigest()
                        if data
                        else None
                    )
                    if recovered and (
                        recovered.get("worker_sha256") != run.manifest.get("worker_sha256")
                        or recovered.get("dataset_sha256") != expected
                    ):
                        recovered = None
                    if recovered and any(
                        recovered.get("source_hashes", {}).get(path) != value
                        for path, value in run.manifest.get("source_hashes", {}).items()
                    ):
                        recovered = None
                    if recovered and run.manifest.get("classification") == "original_execution":
                        from pathlib import Path

                        expected_helper = hashlib.sha256(
                            Path(__file__).with_name("original_worker.py").read_bytes()
                        ).hexdigest()
                        if recovered.get("helper_sha256") != expected_helper:
                            recovered = None
                elif (
                    run.sandbox_id
                    and run.manifest.get("runner") == "e2b"
                    and os.getenv("E2B_API_KEY")
                ):
                    from e2b import AsyncSandbox

                    environment = await AsyncSandbox.connect(
                        run.sandbox_id, api_key=os.environ["E2B_API_KEY"]
                    )
                    await environment.kill()
                elif run.sandbox_id and run.manifest.get("runner") == "docker":
                    proc = await asyncio.create_subprocess_exec(
                        "docker",
                        "rm",
                        "-f",
                        run.sandbox_id,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await asyncio.wait_for(proc.wait(), 10)
                elif (
                    run.sandbox_id
                    and run.manifest.get("runner") == "docker_broker"
                    and settings().runner_url
                ):
                    async with httpx.AsyncClient(timeout=12) as client:
                        await client.delete(
                            settings().runner_url.rstrip("/") + "/executions/" + run.case_id,
                            params={"execution_id": run.id},
                            headers={"Authorization": "Bearer " + settings().runner_token},
                        )
            except Exception:
                recovered = None
            run.status = "completed" if recovered else "interrupted"
            run.output = recovered or {
                "error": "Interrupted environment reconciled. Completed measurements are reused; unfinished work may resume within the remaining budget."
            }
        for job in db.scalars(select(Job).where(Job.state.in_(["running", "interrupted"]))):
            case = db.get(Case, job.case_id)
            if not case or case.status in {"cancelled", "deleting"}:
                continue
            result = dict(case.result or {})
            retries = result.get("_resume_count", 0) + 1
            result["_resume_count"] = retries
            case.result = result
            if retries > 2 or result.get("_elapsed_seconds", 0) >= settings().max_case_seconds:
                job.state = "failed"
                job.error = "Automatic continuation budget exhausted; inspect retained evidence before a manual rerun"
                case.status = "partially_complete"
            else:
                job.state = "queued"
                case.status = "queued"
                emit(
                    db,
                    case.id,
                    "queued",
                    "Resuming from validated checkpoints after environment reconciliation",
                    type="recovery",
                    attempt=retries,
                )
        db.commit()
