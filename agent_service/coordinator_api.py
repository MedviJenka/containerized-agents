from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from agent_service.coordinator import PipelineCoordinator
from agent_service.worker import RunRequest, RunResult
from functions.log import Logger


class JobRequest(BaseModel):
    prompt: str = Field(min_length=1)


class JobAccepted(BaseModel):
    job_id: UUID
    state: str


class HttpWorkerClient:
    def __init__(self, base_url: str, stage: str, shared: Path, timeout: float) -> None:
        self._url = base_url.rstrip("/") + "/run"
        self._stage = stage
        self._shared = shared
        self._timeout = timeout

    def run(self, request: RunRequest) -> RunResult:
        body = json.dumps(
            {"job_id": str(request.job_id), "prompt": request.prompt}
        ).encode("utf-8")
        http_request = urllib.request.Request(
            self._url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(http_request, timeout=self._timeout) as response:
            payload = json.load(response)
        if payload.get("stage") != self._stage:
            raise RuntimeError(
                f"Expected {self._stage} response, received {payload.get('stage')!r}"
            )
        patch_path = self._shared / "jobs" / str(request.job_id) / f"{self._stage}.patch"
        if not patch_path.is_file():
            raise FileNotFoundError(f"Worker did not create {patch_path}")
        return RunResult(
            job_id=request.job_id,
            stage=self._stage,  # type: ignore[arg-type]
            summary=str(payload.get("summary", "")),
            patch_path=patch_path,
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    project = Path(os.environ.get("PROJECT_DIRECTORY", "/project"))
    shared = Path(os.environ.get("SHARED_DIRECTORY", "/shared"))
    timeout = float(os.environ.get("OMP_TASK_TIMEOUT_SECONDS", "1800")) + 30
    app.state.coordinator = PipelineCoordinator(
        project,
        shared,
        HttpWorkerClient(
            os.environ.get("TEAM_1_URL", "http://team_1:8000"),
            "team_1",
            shared,
            timeout,
        ),
        HttpWorkerClient(
            os.environ.get("TEAM_2_URL", "http://team_2:8000"),
            "team_2",
            shared,
            timeout,
        ),
        Logger(name="coordinator"),
    )
    app.state.pipeline_lock = asyncio.Lock()
    app.state.tasks = set()
    try:
        yield
    finally:
        tasks = tuple(app.state.tasks)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="OMP Agent Pipeline", lifespan=lifespan)


async def _execute(request: RunRequest) -> None:
    coordinator: PipelineCoordinator = app.state.coordinator
    lock: asyncio.Lock = app.state.pipeline_lock
    try:
        async with lock:
            await asyncio.to_thread(coordinator.run, request)
    except Exception:  # noqa: BLE001 - job failures are persisted by the coordinator
        # PipelineCoordinator persisted the failure in the job status file.
        return


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_job(job: JobRequest) -> JobAccepted:
    request = RunRequest(job_id=uuid4(), prompt=job.prompt)
    coordinator: PipelineCoordinator = app.state.coordinator
    coordinator.queue(request)
    task = asyncio.create_task(_execute(request))
    app.state.tasks.add(task)
    task.add_done_callback(app.state.tasks.discard)
    return JobAccepted(job_id=request.job_id, state="queued")


@app.get("/jobs/{job_id}")
def get_job(job_id: UUID) -> dict[str, object]:
    shared = Path(os.environ.get("SHARED_DIRECTORY", "/shared"))
    status_path = shared / "jobs" / str(job_id) / "status.json"
    if not status_path.is_file():
        raise HTTPException(status_code=404, detail="Job not found")
    return json.loads(status_path.read_text(encoding="utf-8"))
