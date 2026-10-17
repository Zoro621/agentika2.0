# Release validation — 17 October 2026

Local application: http://127.0.0.1:8000. Deployment/publication is excluded. This record distinguishes live measurements, controlled adapter tests and external prerequisites.

## Automated acceptance

- Backend: 103 tests, covering intake/security, provenance, scientific context/precision, human decisions, original/corrected planning, recovery, private APIs and exports. The final execution-backed-question regression is included.
- Frontend: four unit tests across two files.
- Browser: ten passed — five scenarios on each of desktop 1440×1000 and mobile 360×800 Edge emulation.
- Production TypeScript/Vite build succeeded; API client types regenerated from OpenAPI.
- Browser flows cover source discovery, correspondence decisions, finding review, original source/PDF highlights, exports, clean ZIP control, reduced motion/unavailable WebGL, a 2,000-file virtualized inventory, searchable clusters and actual recorded experiment chart/provenance labels.
- Backend warnings are upstream Starlette TestClient deprecation and scikit-learn’s ineffective `n_jobs` parameter warning. They do not fail acceptance.

Windows parser job tests actually blocked an oversized allocation and terminated a sleeping process when its job closed. Ordinary research code is never executed on the application host. The trusted worker’s numeric tests run locally; original-program tests execute in disposable hosted containers.

## Live GPT-6 Luna and isolated execution

The privately supplied OpenAI key was used without exposing it. A schema-valid GPT-6 Luna response, grounded extraction/adaptive investigation and scanned-page recovery were observed.

| Live check | Observed output |
|---|---|
| Original clean Python script | Accuracy 0.85; actual 600 training / 200 test rows; source hashes unchanged |
| Original notebook, 4-fold CV | Accuracy folds 0.825, 0.815, 0.845, 0.85; mean 0.83375 |
| Human generalization choice | Original baseline 1.0 accuracy, 109 shared entities → corrected grouped 0.5 accuracy, zero shared entities |
| Completed-run reuse | Baseline ID retained after scientific answer; both run IDs retained across the final restart/rerun |
| Network boundary | TCP egress attempt blocked; container policy explicitly disabled |
| Secrets/host boundary | No application credential environment variables; host project path absent |
| Cancellation | Actual allocated container deleted; API confirmed it no longer existed |
| Timeout | Deliberate long-running original program stopped; no successful metrics; container deleted; whole test approximately 84.69 seconds |
| Scanned page | GPT-6 Luna recovered the synthetic page’s 91.2% quantity; provenance and unanswered human confirmation gate retained |

Actual hosted runtime versions: Python 3.13.5, scikit-learn 1.8.0, pandas 2.2.3, NumPy 2.3.5. The application runtime is Python 3.12. Results preserve actual versions rather than assuming equality.

Evidence JSON lives in `docs/validation/`; full local reports/bundles are in `tmp/human-loop-acceptance/`, `tmp/real-paper-audit/`, `tmp/execution-acceptance/` and `tmp/ocr-acceptance/`. The numerical human-loop fixture is explicitly synthetic. Original execution, reconstruction and changed-protocol evaluation have distinct provenance.

The final live integration also exposed a graph bug for execution-backed scientific questions. It was fixed, regression-tested and the case resumed with its original completed measurements. The opt-in test now rejects failed/cancelled terminal states instead of accepting the presence of metrics alone.

## Actual published-paper audit

Publication: [MLxtend, JOSS 3(24), 638 (2018)](https://joss.theoj.org/papers/10.21105/joss.00638). Repository: `rasbt/mlxtend`, `v0.11.0`, pinned commit `f08e9e65e6acf66910c626a434dda85eb552bb9d`.

The actual PDF and complete accepted repository source archive passed the private API workflow with GPT-6 Luna. The final run inventoried **266 files**, inspected **97**, recorded **three unavailable empty CSVs**, examined **two independently grounded paper claims**, and retained **18 incomplete/inconclusive checks**. Three PDF pages were inspected across the publication and a repository example; the publication itself is two pages. The separately uploaded paper was automatically selected over repository example/figure PDFs.

**No verified contradiction was found. No corresponding single empirical benchmark was established, and no numerical reproduction was claimed.** This software paper primarily describes capabilities. The unresolved dataset correspondence, missing execution prerequisites and 100-file inspection budget are visible. Zero conclusive numerical checks is not evidence of overall correctness.

GitHub’s unauthenticated API was rate-limited. The acceptance script downloaded the previously verified commit archive directly, uploaded its source ZIP and recorded URL/commit/archive/PDF hashes in the provenance sidecar. This fallback is explicit; the application itself still presents actionable GitHub rate-limit errors. The chosen historical tag is not asserted to be the exact publication snapshot.

## Interface and report review

The previous visual interface is restored; the newer interactive camera view and controls were removed. The optional earlier spatial graph remains, with 2D as default. Original PDF pages, highlighted citations, mobile layouts and final PDF report pages were rendered and visually inspected. Reports include provider/model, coverage, source claims, completed/incomplete checks, findings, alternatives, human decisions and actual run provenance.

Critical JavaScript is approximately **140.68 kB gzip**, CSS **13.60 kB gzip**. Three.js scene (~248.93 kB gzip), charts and PDF view are deferred. A Vite large-chunk advisory remains for the deferred scene.

The documented cold mobile lab profile uses 360×800, 4× CPU slowdown, 4 Mbps down / 1 Mbps up and 100 ms latency. It measured **1,228 ms LCP**, **0.01781 CLS** and **168 ms maximum observed interaction duration**. This is one local lab visit with settings interactions, not field INP or a Lighthouse score. Physical-device/public-service performance remains an environment-specific certification step.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm test
npm run build
npm run types:api
# Offline browser-test server on port 8001; use a separate data directory.
$env:CB_TEST_URL='http://127.0.0.1:8001'
npm run test:e2e
node scripts/measure-ui.mjs
```

Opt-in live scripts use the configured private key and incur model/container charges: `verify-live-model.py`, `verify-live-sandbox.py`, `verify-live-notebook.py`, `verify-live-boundaries.py`, `verify-live-timeout.py`, `verify-live-ocr.py`, `verify-human-loop.py`, `verify-real-audit.py`.

## External prerequisites and excluded work

Live acceptance used OpenAI plus SQLite/private filesystem. Ollama is not installed; Docker’s engine remains unavailable; E2B and Supabase/PostgreSQL credentials were absent. Their controlled adapter/offline/broker tests do not certify live external services. Alternate Clouds deployment, registry publication, public HTTPS/proxy checks, cloud persistence certification and deployment-dependent submission steps were excluded. No public deployment or remote CI run is claimed.
