from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent_service.rpc_client import OmpRpcClient
from agent_service.worker import AgentWorker, RunRequest, WorkerSettings
from functions.log import Logger


class WorkerApiRequest(BaseModel):
    job_id: UUID
    prompt: str = Field(min_length=1)


class WorkerApiResponse(BaseModel):
    job_id: UUID
    stage: str
    summary: str
    patch_path: str


def _settings() -> WorkerSettings:
    raw_stage = os.environ.get("AGENT_STAGE", "")
    if raw_stage not in {"team_1", "team_2"}:
        raise RuntimeError("AGENT_STAGE must be team_1 or team_2")
    stage = cast(Literal["team_1", "team_2"], raw_stage)
    return WorkerSettings(
        stage=stage,
        project=Path(os.environ.get("PROJECT_DIRECTORY", "/project")),
        workspace=Path(os.environ.get("WORKSPACE_DIRECTORY", "/work/current")),
        shared=Path(os.environ.get("SHARED_DIRECTORY", "/shared")),
    )


def _omp_command(settings: WorkerSettings) -> list[str]:
    state_directory = Path(os.environ.get("OMP_STATE_DIRECTORY", "/home/agent/.omp"))
    state_directory.mkdir(parents=True, exist_ok=True)
    command = [
        "omp",
        "--mode",
        "rpc",
        "--cwd",
        str(settings.workspace),
        "--session-dir",
        str(state_directory / "sessions"),
        "--no-title",
        "--yolo",
    ]
    if model := os.environ.get("OMP_MODEL"):
        command.extend(("--model", model))
    return command


def _load_provider_secrets() -> None:
    if secret_path := os.environ.get("OPENAI_API_KEY_FILE"):
        value = Path(secret_path).read_text(encoding="utf-8").strip()
        if not value:
            raise RuntimeError("OPENAI_API_KEY_FILE is empty")
        os.environ["OPENAI_API_KEY"] = value


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = _settings()
    _load_provider_secrets()
    settings.workspace.mkdir(parents=True, exist_ok=True)
    rpc = OmpRpcClient(
        _omp_command(settings),
        timeout=float(os.environ.get("OMP_TASK_TIMEOUT_SECONDS", "1800")),
    )
    app.state.worker = AgentWorker(settings, rpc, Logger(name=settings.stage))
    app.state.worker_lock = asyncio.Lock()
    try:
        yield
    finally:
        rpc.close()


app = FastAPI(title="OMP Agent Worker", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run", response_model=WorkerApiResponse)
async def run(request: WorkerApiRequest) -> WorkerApiResponse:
    worker: AgentWorker = app.state.worker
    lock: asyncio.Lock = app.state.worker_lock
    try:
        async with lock:
            result = await asyncio.to_thread(
                worker.run,
                RunRequest(job_id=request.job_id, prompt=request.prompt),
            )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return WorkerApiResponse(
        job_id=result.job_id,
        stage=result.stage,
        summary=result.summary,
        patch_path=str(result.patch_path),
    )
