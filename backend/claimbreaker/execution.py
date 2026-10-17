import asyncio
import hashlib
import json
import os
import shutil
import math
import httpx
from pathlib import Path
from .config import settings

ACTIVE = {}


def validate_result(result, csv):
    expected = hashlib.sha256(
        Path(__file__).with_name("sandbox_worker.py").read_text(encoding="utf-8").encode()
    ).hexdigest()
    if result.get("worker_sha256") != expected:
        raise RuntimeError(
            "Runner code hash differs from this release. Rebuild the Docker image or E2B template before running again."
        )
    if result.get("dataset_sha256") != hashlib.sha256(csv.encode()).hexdigest():
        raise RuntimeError("Runner input hash did not match the requested dataset")
    metrics = result.get("metrics", {})
    if not metrics or any(
        not isinstance(v, (int, float)) or not math.isfinite(v) for v in metrics.values()
    ):
        raise RuntimeError("Runner did not return valid finite measurements")
    return result


async def runner_status():
    cfg = settings()
    if cfg.runner == "none":
        return {
            "available": False,
            "provider": "none",
            "reason": "Execution disabled by configuration",
        }
    if cfg.runner_url and cfg.runner in {"auto", "docker", "broker"}:
        try:
            async with httpx.AsyncClient(timeout=4) as client:
                response = await client.get(
                    cfg.runner_url.rstrip("/") + "/capabilities",
                    headers={"Authorization": "Bearer " + cfg.runner_token},
                )
                response.raise_for_status()
                result = response.json()
                return {**result, "provider": "docker_broker"}
        except (httpx.HTTPError, ValueError):
            return {
                "available": False,
                "provider": "docker_broker",
                "reason": "Local Docker broker is unavailable or its private token does not match",
            }
    if not cfg.offline and os.getenv("E2B_API_KEY") and cfg.runner in {"auto", "e2b"}:
        return {"available": True, "provider": "e2b", "reason": "Remote isolated runner configured"}
    if shutil.which("docker") and cfg.runner in {"auto", "docker"}:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "image",
                "inspect",
                cfg.docker_image,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), 4)
            if proc.returncode == 0:
                return {
                    "available": True,
                    "provider": "docker",
                    "reason": "Restricted local runner image ready",
                }
        except (OSError, TimeoutError):
            pass
    if not cfg.offline and os.getenv("OPENAI_API_KEY") and cfg.runner in {"auto", "openai"}:
        return {
            "available": True,
            "provider": "openai",
            "reason": "Disposable hosted Python sandbox, 1 GB memory, network disabled",
        }
    return {
        "available": False,
        "provider": "none",
        "reason": "Start Docker and build the runner image, or configure E2B. Saved results and deterministic checks remain available.",
    }


async def run_isolated(case_id, execution_id, csv, spec, on_started=None):
    capability = await runner_status()
    if not capability["available"]:
        raise RuntimeError(capability["reason"])
    payload = json.dumps({"csv": csv, "spec": spec}).encode()
    if capability["provider"] == "openai":
        from .openai_sandbox import execute

        def started(ref):
            ACTIVE[case_id] = ("openai", ref)
            if on_started:
                on_started(ref)

        try:
            measured = await asyncio.wait_for(execute({"csv": csv, "spec": spec}, started), 90)
            return validate_result(measured, csv)
        finally:
            await terminate(case_id)
    if capability["provider"] == "docker_broker":
        ACTIVE[case_id] = ("broker", execution_id)
        if on_started:
            on_started(execution_id)
        try:
            async with httpx.AsyncClient(timeout=105) as client:
                response = await client.post(
                    settings().runner_url.rstrip("/") + "/executions",
                    headers={"Authorization": "Bearer " + settings().runner_token},
                    json={
                        "case_id": case_id,
                        "execution_id": execution_id,
                        "csv": csv,
                        "spec": spec,
                    },
                )
                response.raise_for_status()
                return validate_result(response.json(), csv)
        finally:
            await terminate(case_id)
    if capability["provider"] == "docker":
        name = "claimbreaker-" + execution_id
        args = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--name",
            name,
            "--network",
            "none",
            "--cpus",
            "1",
            "--memory",
            "768m",
            "--pids-limit",
            "64",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=128m",
            "--user",
            "65534:65534",
            "-e",
            "OPENBLAS_NUM_THREADS=1",
            "-e",
            "OMP_NUM_THREADS=1",
            settings().docker_image,
        ]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        ACTIVE[case_id] = ("docker", name)
        if on_started:
            on_started(name)
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(payload), 90)
            if proc.returncode:
                raise RuntimeError(
                    "Runner exited without a successful result: "
                    + stderr.decode(errors="replace")[-1200:]
                )
            if len(stdout) > 200000:
                raise RuntimeError("Runner output limit exceeded")
            if not stdout.strip():
                raise RuntimeError("Runner failed: " + stderr.decode(errors="replace")[-1500:])
            result = json.loads(stdout.decode().splitlines()[-1])
            if not result.get("ok"):
                raise RuntimeError(result.get("error", "Execution failed"))
            return validate_result(result["result"], csv)
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            await terminate(case_id)
    from e2b import AsyncSandbox

    sandbox = await AsyncSandbox.create(
        template=settings().e2b_template,
        api_key=os.environ["E2B_API_KEY"],
        timeout=120,
        allow_internet_access=False,
    )
    ACTIVE[case_id] = ("e2b", sandbox)
    if on_started:
        on_started(sandbox.sandbox_id)
    try:
        worker = Path(__file__).with_name("sandbox_worker.py").read_text()
        await sandbox.files.write("/tmp/cb_worker.py", worker)
        await sandbox.files.write(
            "/tmp/original_worker.py", Path(__file__).with_name("original_worker.py").read_text()
        )
        await sandbox.files.write("/tmp/cb_input.json", payload.decode())
        # Fixed command; neither project text nor model output enters command arguments.
        result = await asyncio.wait_for(
            sandbox.commands.run(
                "CB_ISOLATED_EXECUTION=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -I /tmp/cb_worker.py < /tmp/cb_input.json",
                timeout=90,
            ),
            95,
        )
        stdout = result.stdout
        if len(stdout) > 200000:
            raise RuntimeError("Runner output limit exceeded")
        parsed = json.loads(stdout.splitlines()[-1])
        if not parsed.get("ok"):
            raise RuntimeError(parsed.get("error", "Execution failed"))
        return validate_result(parsed["result"], csv)
    finally:
        await terminate(case_id)


async def terminate(case_id):
    active = ACTIVE.pop(case_id, None)
    if not active:
        return
    kind, ref = active
    if kind == "docker":
        try:
            for attempt in range(3):
                proc = await asyncio.create_subprocess_exec(
                    "docker",
                    "rm",
                    "-f",
                    ref,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                try:
                    await asyncio.wait_for(proc.wait(), 4)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
                    break
                if proc.returncode == 0:
                    break
                if attempt < 2:
                    await asyncio.sleep(0.3)
        except (OSError, TimeoutError):
            pass
    elif kind == "openai":
        from .openai_sandbox import destroy

        await destroy(ref)
    elif kind == "broker":
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                await client.delete(
                    settings().runner_url.rstrip("/") + "/executions/" + case_id,
                    params={"execution_id": ref},
                    headers={"Authorization": "Bearer " + settings().runner_token},
                )
        except httpx.HTTPError:
            pass
    else:
        try:
            await asyncio.wait_for(ref.kill(), 10)
        except Exception:
            pass


from .execution_planning import execution_plan, execution_questions
