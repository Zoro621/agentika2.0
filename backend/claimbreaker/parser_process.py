import asyncio
import base64
import json
import os
import sys
import hashlib
from pathlib import Path

PARSER_FINGERPRINT = hashlib.sha256(
    b"".join(
        Path(__file__).with_name(name).read_bytes()
        for name in ("parsing.py", "checks.py", "parse_worker.py", "pdf_tools.py")
    )
).hexdigest()


async def parse_bounded(artifact, data, page_budget=None, **operation):
    env = os.environ.copy()
    # Parsing needs no service credentials. Preserve only runtime/environment configuration.
    for key in list(env):
        if any(
            word in key.upper()
            for word in ("API_KEY", "TOKEN", "SECRET", "SERVICE_KEY", "DATABASE_URL")
        ):
            env.pop(key, None)
    env.update(
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        CB_PARSER_MODE="1",
        CB_SESSION_SECRET="parser-process",
    )
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "claimbreaker.parse_worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    job = None
    try:
        if os.name == "nt":
            from .windows_limits import parser_job

            job = parser_job(proc.pid)
        payload = json.dumps(
            {
                "artifact": {
                    "id": artifact.id,
                    "path": artifact.path,
                    "kind": artifact.kind,
                    "page_budget": page_budget,
                },
                "data": base64.b64encode(data).decode(),
                **operation,
            }
        ).encode()
        stdout, stderr = await asyncio.wait_for(proc.communicate(payload), 35)
        if proc.returncode or len(stdout) > 8 * 1024**2:
            raise ValueError("Parser resource or output limit reached")
        result = json.loads(stdout)
        result["parser_fingerprint"] = PARSER_FINGERPRINT
        return result
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        if job:
            job.close()
