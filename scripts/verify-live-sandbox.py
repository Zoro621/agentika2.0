"""Opt-in live isolated baseline smoke test using the privately configured key."""

import asyncio
import io
import json
import zipfile
import sys
import base64
from claimbreaker.samples import build_sample
from claimbreaker.openai_sandbox import execute
from claimbreaker.execution import validate_result


async def main():
    source = zipfile.ZipFile(io.BytesIO(build_sample("clean")))
    csv = source.read("cohort.csv").decode()
    from claimbreaker.parsing import code_profile

    profile = code_profile(source.read("train.py").decode())
    spec = {
        "target": profile["target"],
        "features": profile["features"],
        "estimator": profile["estimator"],
        "params": profile["params"],
        "variant": "baseline",
        "seed": 42,
        "test_size": 0.25,
    }
    if "--original" in sys.argv:
        spec.update(
            execution_mode="original",
            entry_path="train.py",
            entity="person_id",
            source_files=[
                {"path": name, "data": base64.b64encode(source.read(name)).decode()}
                for name in source.namelist()
                if name.endswith((".py", ".csv"))
            ],
        )
    result = validate_result(await execute({"csv": csv, "spec": spec}), csv)
    from pathlib import Path

    Path("tmp/live-sandbox.json").write_text(json.dumps(result, indent=2))
    print(
        json.dumps(
            {
                "metrics": result["metrics"],
                "environment": result.get("environment"),
                "sandbox": result["sandbox"],
            }
        )
    )


asyncio.run(main())
