"""One-time E2B image build, before running with network access disabled."""

import os
from pathlib import Path
from e2b import Template
from dotenv import load_dotenv

root = Path(__file__).resolve().parents[1]
load_dotenv(root / ".env", override=False)
if not os.getenv("E2B_API_KEY"):
    raise SystemExit("Set E2B_API_KEY privately before building the runner template")

deps = " ".join((root / "runner/requirements.lock").read_text().splitlines())
template = Template().from_python_image("3.12").run_cmd("pip install --no-cache-dir " + deps)
Template.build(
    template,
    "claimbreaker-cpu-v1",
    cpu_count=1,
    memory_mb=1024,
    on_build_logs=lambda logs: print(logs),
)
print("Set CB_E2B_TEMPLATE=claimbreaker-cpu-v1 on the application service.")
