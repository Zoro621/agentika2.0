# ClaimBreaker — the Evidence Observatory

A private research investigation workspace for Agentika’s **Human in the Loop** theme. Drop a ZIP/PDF or connect a public GitHub repository. ClaimBreaker discovers artifacts, extracts source claims, traces evidence, runs supported checks and asks scientific questions whose answers change the investigation.

## Run locally

Python 3.12, Node 24 and npm are required.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
npm ci --legacy-peer-deps
npm run build
.\scripts\start.ps1
```

Open **http://127.0.0.1:8000**. FastAPI serves the production frontend and API. For development, `npm run dev` starts Vite with an API proxy. On Unix, use the equivalent virtual-environment commands and `sh scripts/start.sh`.

Copy `.env.example` to `.env` for private configuration. The supplied private key is configured locally; no credential belongs in source control or the browser. Cases belong to the current browser session and expire after seven days. Clearing cookies removes access to those private cases.

## Restored interface

The previous layout is restored: the restrained paper/orbit hero, the **2D evidence graph by default**, and the earlier optional **Spatial view**. The recently added interactive camera interface and its controls are removed. Lazy graphics, reduced-motion and WebGL fallbacks remain.

Source inspection includes rendered original PDF pages with cited text/table highlights. Large source/activity lists are virtualized. Large graphs group real stored nodes into searchable clusters. Desktop and mobile support intake, source inspection, scientific decisions, runs, review and exports.

## Models and actual execution

- `OPENAI_API_KEY` enables hosted inference. `CB_OPENAI_MODEL=gpt-6-luna` is the default; the Responses API uses validated schemas and `store=false`.
- `CB_RUNNER=auto` can use the supplied key for disposable OpenAI Python containers: 1 GB memory, network disabled, exact trusted coordinator, downloaded measurement files and actual environment/source/input/worker hashes. Containers are deleted on completion, timeout and cancellation.
- Supported original CPU Python/notebook programs run only inside isolation. Reconstructions, corrected evaluations and original executions have distinct labels. There is no dependency installation or host execution of research code.
- Cross-validation, grouped/chronological corrections, feature-availability and training-only-preprocessing corrections use established prerequisites. Ambiguity produces a question or an inconclusive check.
- Ollama: install it and download `qwen3:8b`; set `CB_PROVIDER=ollama`. Endpoint/model are configurable. Automatic fallback requires a reachable configured model.
- Offline: preinstall dependencies/model/runner, start Docker, build the image below, then run `scripts/start.ps1 -Offline`. External retrieval/inference are disabled. Ollama and Docker are not currently available on this machine; live acceptance used OpenAI execution.

```powershell
docker build -f runner/Dockerfile -t claimbreaker-runner:0.1.0 .
```

The containerized offline profile in `compose.yaml` uses an authenticated host runner broker. Configure a random `CB_RUNNER_TOKEN` of at least 32 characters, start `claimbreaker.runner_service:app` on port 7071 privately, then `docker compose up --build`. Experiment containers receive no host mounts, credentials or Docker socket. E2B is also supported after building `scripts/build-e2b.py` and configuring its key/template.

## Human judgment and evidence

Try **The generalization gap**, wait for the original baseline, and answer **New individuals**. Live acceptance measured **100% → 50% accuracy**, **109 → 0 shared entities**, and reused the completed baseline. These are actual computations on the explicitly synthetic fixture, not published research.

Claims and findings retain exact source anchors, observed values, checks, alternatives, limitations and review history. Trial summaries, source correspondence, feature timing and intended deployment remain scientific decisions. Scanned-page quantities require human confirmation. A difference never automatically becomes a contradiction or a misconduct verdict.

Exports include PDF, complete JSON and a source/manifest/measured-output ZIP. Unsupported or incomplete checks remain visible. The initial inspection budget is 100 prioritized files, while every accepted file is inventoried.

## Validation

The full API workflow was tested with the actual [MLxtend JOSS publication](https://joss.theoj.org/papers/10.21105/joss.00638) and pinned public repository `f08e9e65e6acf66910c626a434dda85eb552bb9d`. It is a software paper with no established single corresponding benchmark. The report makes no verified contradiction or reproduction claim.

Local outputs: `tmp/real-paper-audit/`, `tmp/human-loop-acceptance/`, `tmp/execution-acceptance/`. Opt-in `scripts/verify-live-*.py`, `verify-human-loop.py` and `verify-real-audit.py` make real API/container calls and can incur charges. Unit/browser tests use controlled/offline profiles.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm test
npm run build
npm run types:api
# Start the application first; Edge is the default browser.
npm run test:e2e
```

See [implementation](docs/IMPLEMENTATION.md), [scope and prerequisites](docs/REMAINING_WORK.md), [validation evidence](docs/VALIDATION.md), and [completion tracker](docs/COMPLETION_TRACKER.md).

## Deployment excluded from this request

Nothing has been deployed or published. Alternate Clouds deployment files and [instructions](docs/DEPLOYMENT.md) remain available, together with the handbook/demo [submission checklist](docs/DEMO.md). Cloud persistence, public proxy behavior and field performance require their configured deployment environment.
