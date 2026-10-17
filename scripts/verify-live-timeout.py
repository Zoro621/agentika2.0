"""Live timeout kills computation and tears down the actual environment."""

import asyncio, base64, json, os, time
from pathlib import Path
import httpx
from claimbreaker.openai_sandbox import execute, API


async def main():
    refs = []
    started = time.monotonic()
    error = ""
    source = b"import time\ntime.sleep(120)\n"
    spec = {
        "execution_mode": "original",
        "entry_path": "timeout.py",
        "source_files": [{"path": "timeout.py", "data": base64.b64encode(source).decode()}],
    }
    try:
        await execute({"csv": "x,y\n1,0\n", "spec": spec}, refs.append)
        raise AssertionError("A timed out program returned successful measurements")
    except (RuntimeError, TimeoutError) as exc:
        error = str(exc)
    assert refs and (not error or "tim" in error.lower()), error
    async with httpx.AsyncClient(
        timeout=15, headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}
    ) as client:
        assert (await client.get(API + "/containers/" + refs[0])).status_code == 404
    result = {
        "seconds": round(time.monotonic() - started, 2),
        "successful_metrics": False,
        "environment_deleted": True,
        "error": error or "Coordinator wall timeout",
    }
    Path("tmp/execution-acceptance/timeout.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


asyncio.run(main())
