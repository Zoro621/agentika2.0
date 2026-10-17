# Alternate Clouds deployment

Deploy one application replica and one Uvicorn worker. The API owns a single durable queue consumer. Multiple replicas require a database lease/claim mechanism before scaling; do not scale this release horizontally.

## 1. Prepare the services

Create a Supabase PostgreSQL database and a **private** Storage bucket named `claimbreaker`. Use its server-only service role key. Set a stable random `CB_SESSION_SECRET` before the first public launch. Use the PostgreSQL pooler's **session** connection string with SQLAlchemy's `postgresql+psycopg://` scheme; include `?sslmode=require`.

Prepare an E2B template containing Python 3.12 and the pinned packages in `runner/requirements.lock`:

```powershell
# Reads E2B_API_KEY from the process environment or the private root .env file.
.\.venv\Scripts\python.exe scripts/build-e2b.py
```

Configure a hosted model key, or an Ollama service reachable from the deployed application. A laptop's localhost is not reachable from a cloud container.

## 2. Build an immutable image

If Docker cannot build locally, push the reviewed repository to your GitHub namespace and run the included **Build versioned release image** workflow manually. It publishes a commit-based GHCR tag. Change that package's visibility to public before Alternate Clouds pulls it. The separate verification workflow runs backend, frontend and Chromium acceptance checks on Linux.

```powershell
# Substitute your public registry namespace and release commit/tag.
docker build -t ghcr.io/YOUR_TEAM/claimbreaker:RELEASE_COMMIT .
docker push ghcr.io/YOUR_TEAM/claimbreaker:RELEASE_COMMIT
```

The image must be public or otherwise pullable by Alternate Clouds. The application runs as UID 10001 and listens on port **8000**. The frontend is included in the image. No Docker socket is required by the hosted profile.

## 3. Authenticate and deploy

```powershell
npm install -g @alternatefutures/acc
acc login
acc whoami
acc projects create --name claimbreaker
acc projects list
.\scripts\deploy-alternate.ps1 -Image ghcr.io/YOUR_TEAM/claimbreaker:RELEASE_COMMIT
```

For a preselected project/automation, the official CLI supports private `AF_TOKEN` and `AF_PROJECT_ID` environment variables. Select the intended project before creating a service. Use the dashboard to set resources and secrets without putting secret values into shell history. Start with 2 CPU / 4 GB memory for parsing and experiment coordination; E2B provides the separate execution resources. Set a spend limit appropriate to your credits.

The deployment helper also loads `AF_TOKEN` and `AF_PROJECT_ID` from the private root `.env` file without printing them. Existing process variables take precedence. These CLI credentials are separate from the application's service environment below; the script does not transfer the entire `.env` file into a public deployment.

Required service environment:

| Variable | Value |
|---|---|
| `CB_DATABASE_URL` | Private PostgreSQL connection string |
| `CB_SUPABASE_URL` | Your project's HTTPS endpoint |
| `CB_SUPABASE_SERVICE_KEY` | Private service key |
| `CB_STORAGE_BUCKET` | `claimbreaker` (private bucket) |
| `CB_SESSION_SECRET` | Stable random secret |
| `CB_SECURE_COOKIES` | `true` |
| `CB_OFFLINE` | `false` |
| `CB_RUNNER` | `e2b` |
| `E2B_API_KEY` | Private sandbox key |
| `CB_E2B_TEMPLATE` | `claimbreaker-cpu-v1` |
| `OPENAI_API_KEY` | Private hosted model key |
| `CB_OPENAI_MODEL` | `gpt-6-luna` or configured supported model |
| `GITHUB_TOKEN` | Optional read-only public-repository access |

Run `alembic upgrade head` against a new configured database before the application's first deployment. The first-release application also creates initial tables on startup for local ease. An already bootstrapped local database can be stamped `0001` only after confirming it matches the initial schema; do not run an initial create-table migration over existing tables. Future schema changes require new migration revisions. Case sources are uploaded to private object storage before their metadata commits. Local disk is a cache; PostgreSQL and private object storage are authoritative for hosted recovery.

## 4. Validate the public service

```powershell
acc services list
acc services info
acc services logs --tail 100
```

On the HTTPS public URL, verify all of these before submission:

1. `/api/v1/health/live` and `/api/v1/health/ready` return success.
2. `/api/v1/capabilities` shows the intended model and execution provider.
3. A ZIP uploads; SSE remains live through the proxy (`X-Accel-Buffering: no`).
4. The synthetic baseline actually completes in E2B; a human decision produces a second run.
5. A PDF opens its source, a result mismatch is explained, and a PDF report downloads.
6. A second browser cannot open the first browser's case ID.
7. Restart the service: persisted cases and decisions remain available with the same session secret. An interrupted run is reconciled and requires an explicit rerun; completed execution fingerprints are reused.
8. Test on a phone, then delete a test case and verify the objects are removed.

Keep the stable application URL for judges. Use a new versioned image tag for every release. Do not rely on `latest` or `main`; providers cache tags.

Sources verified during implementation: [official CLI quickstart](https://docs.alternatefutures.ai/guides/quickstart), [deployment lifecycle and tag behavior](https://docs.alternatefutures.ai/guides/how-deployments-work).

## Environment status

At implementation time, no deployment, model, GitHub, Supabase or E2B credentials were present. Docker Desktop's client was installed, but its Linux engine failed startup because an internal telemetry socket could not be accessed. Starting/stopping Docker and attempting removal of that single verified stale socket did not repair the engine. No container execution or image build is claimed. The repository includes production source, image/workflow configuration and deployment commands; a public URL must be validated after service configuration. Live PostgreSQL, Supabase, E2B, provider and offline-runtime checks remain separate release gates.

