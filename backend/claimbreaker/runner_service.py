"""Local host broker for a containerized offline application.

This trusted coordinator owns Docker access; experiment containers never do.
Only the fixed worker and validated data/specifications enter a sandbox.
"""

import asyncio
import secrets
from collections import deque
from contextlib import asynccontextmanager
from uuid import UUID
from typing import Literal
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from .config import settings
from .execution import runner_status, run_isolated, terminate
from .http_limits import BodyLimitMiddleware

TASKS = {}
CURRENT = {}
CANCELLED = deque(maxlen=4096)
LOCK = asyncio.Lock()


class Specification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str = Field(max_length=100)
    code_id: str = Field(max_length=100)
    target: str = Field(max_length=200)
    features: list[str] = Field(max_length=200)
    estimator: Literal[
        "LogisticRegression",
        "RandomForestClassifier",
        "RandomForestRegressor",
        "DecisionTreeClassifier",
        "LinearRegression",
        "Ridge",
    ]
    params: dict[str, str | float | int | bool | None] = Field(default_factory=dict, max_length=30)
    seed: int | None = None
    seed_origin: str = "source"
    test_size: float = Field(default=0.25, ge=0.05, le=0.5)
    entity: str | None = None
    scaling: bool = False
    stratify: bool = False
    imputer_strategy: Literal["median", "mean", "most_frequent"] = "median"
    exclude: list[str] = Field(default_factory=list, max_length=200)
    variant: Literal[
        "baseline", "grouped", "corrected_features", "corrected_preprocessing", "temporal"
    ]
    split_mode: Literal["random", "grouped", "temporal", "grouped_temporal"] = "random"
    time_column: str | None = None
    execution_mode: Literal["original", "reconstruction"] = "reconstruction"
    entry_path: str = ""
    preprocessing_policy: Literal["as_source", "training_only"] = "training_only"
    source_files: list[dict[str, str]] = Field(default_factory=list, max_length=200)
    cv: dict | None = None


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    execution_id: UUID
    csv: str = Field(max_length=100 * 1024**2)
    spec: Specification


@asynccontextmanager
async def lifespan(app):
    cfg = settings()
    if len(cfg.runner_token) < 32:
        raise RuntimeError("Configure a private CB_RUNNER_TOKEN of at least 32 characters")
    cfg.runner_url = ""
    cfg.runner = "docker"
    cfg.offline = True
    yield
    for case_id, task in list(TASKS.items()):
        task.cancel()
        await terminate(case_id)


app = FastAPI(
    title="ClaimBreaker local Docker broker",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_middleware(BodyLimitMiddleware, default_limit=105 * 1024**2)


@app.middleware("http")
async def authorize(request: Request, call_next):
    from fastapi.responses import JSONResponse

    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not settings().runner_token or not secrets.compare_digest(token, settings().runner_token):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    # BodyLimitMiddleware bounds both declared and streamed bytes before decoding.
    return await call_next(request)


@app.get("/capabilities")
async def capabilities():
    return await runner_status()


@app.post("/executions")
async def execute(payload: Payload):
    case_id = str(payload.case_id)
    if str(payload.execution_id) in CANCELLED:
        raise HTTPException(409, "Execution was cancelled before startup")
    if LOCK.locked():
        raise HTTPException(429, "One local execution is already running")
    async with LOCK:
        task = asyncio.create_task(
            run_isolated(case_id, str(payload.execution_id), payload.csv, payload.spec.model_dump())
        )
        TASKS[case_id] = task
        CURRENT[case_id] = str(payload.execution_id)
        try:
            return await task
        except asyncio.CancelledError:
            raise HTTPException(409, "Execution cancelled")
        except Exception as exc:
            raise HTTPException(422, str(exc)[:1000])
        finally:
            TASKS.pop(case_id, None)
            CURRENT.pop(case_id, None)
            await terminate(case_id)


@app.delete("/executions/{case_id}")
async def cancel(case_id: UUID, execution_id: UUID | None = None):
    key = str(case_id)
    if execution_id:
        CANCELLED.append(str(execution_id))
    task = TASKS.get(key)
    if task and (not execution_id or CURRENT.get(key) == str(execution_id)):
        task.cancel()
        await terminate(key)
    return {"cancelled": True}
