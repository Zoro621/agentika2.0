"""Live hosted isolation boundary and cancellation acceptance."""

import asyncio, json, os
from pathlib import Path
import httpx
from claimbreaker.config import settings
from claimbreaker.openai_sandbox import API, destroy, execute


async def main():
    headers = {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}
    async with httpx.AsyncClient(headers=headers, timeout=60) as client:
        r = await client.post(
            API + "/containers",
            json={
                "name": "claimbreaker-boundary-test",
                "memory_limit": "1g",
                "network_policy": {"type": "disabled"},
                "expires_after": {"anchor": "last_active_at", "minutes": 20},
            },
        )
        r.raise_for_status()
        container = r.json()
        id = container["id"]
        try:
            probe = "import socket,os,json,pathlib\ns=socket.socket();s.settimeout(3)\ntry:\n s.connect(('1.1.1.1',443));connected=True\nexcept OSError:\n connected=False\nfinally:\n s.close()\npathlib.Path('/mnt/data/boundary.json').write_text(json.dumps({'network_connected':connected,'application_secrets_present':any(k in os.environ for k in ['OPENAI_API_KEY','E2B_API_KEY','GITHUB_TOKEN','SUPABASE_SERVICE_KEY']),'host_project_visible':os.path.exists('C:/Users/emadh/OneDrive/Desktop/nascon/.env')}))"
            r = await client.post(
                API + "/responses",
                json={
                    "model": settings().openai_model,
                    "reasoning": {"effort": "none"},
                    "store": False,
                    "tools": [{"type": "code_interpreter", "container": id}],
                    "tool_choice": "required",
                    "max_tool_calls": 1,
                    "max_output_tokens": 1500,
                    "input": "Execute this exact trusted boundary probe unchanged, using the Python tool once:\n"
                    + probe,
                },
            )
            r.raise_for_status()
            calls = [c for c in r.json()["output"] if c["type"] == "code_interpreter_call"]
            assert len(calls) == 1 and calls[0]["code"].strip() == probe.strip()
            listing = (await client.get(f"{API}/containers/{id}/files")).json()
            file = next(f for f in listing["data"] if f["path"] == "/mnt/data/boundary.json")
            result = await client.get(f"{API}/containers/{id}/files/{file['id']}/content")
            result.raise_for_status()
            boundary = result.json()
            assert not any(boundary.values())
        finally:
            await destroy(id)
        assert (await client.get(API + "/containers/" + id)).status_code == 404
        boundary.update(
            network_policy=container["network_policy"],
            memory_limit=container["memory_limit"],
            teardown_verified=True,
        )
        started = asyncio.Event()
        references = []

        def created(id):
            references.append(id)
            started.set()

        task = asyncio.create_task(execute({"csv": "x,y\n1,0\n", "spec": {}}, created))
        await asyncio.wait_for(started.wait(), 15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert (await client.get(API + "/containers/" + references[0])).status_code == 404
        boundary["cancellation_destroyed_environment"] = True
        root = Path("tmp/execution-acceptance")
        root.mkdir(exist_ok=True)
        (root / "boundaries.json").write_text(json.dumps(boundary, indent=2))
        print(json.dumps(boundary))


asyncio.run(main())
