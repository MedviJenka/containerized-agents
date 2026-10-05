import json
import os
from pathlib import Path
from typing import Protocol
from agent_service.worker import RunRequest, RunResult
from agent_service.workspace import apply_patch


class WorkerClient(Protocol):
    def run(self, request: RunRequest) -> RunResult: ...


class PipelineCoordinator:
    def __init__(self, project: Path, shared: Path, team_1: WorkerClient, team_2: WorkerClient, logger: Logger) -> None:
        self._project = project
        self._shared = shared
        self._team_1 = team_1
        self._team_2 = team_2
        self._logger = logger

    def queue(self, request: RunRequest) -> None:
        job_directory = self._shared / "jobs" / str(request.job_id)
        job_directory.mkdir(parents=True, exist_ok=False)
        self._write_status(job_directory, "queued")
        self._logger.fire("Job queued", job_id=str(request.job_id))

    def run(self, request: RunRequest) -> None:

        job_directory = self._shared / "jobs" / str(request.job_id)
        job_directory.mkdir(parents=True, exist_ok=True)
        context = {"job_id": str(request.job_id)}
        self._logger.fire("Pipeline started", **context)

        try:
            self._write_status(job_directory, "team_1_running")
            self._logger.fire("Team 1 started", **context)
            first = self._team_1.run(request)
            self._logger.fire("Team 1 completed", **context)
            self._write_status(job_directory, "team_2_running", team_1_summary=first.summary)
            self._logger.fire("Team 2 started", **context)
            second = self._team_2.run(request)
            self._logger.fire("Team 2 completed", **context)
            self._write_status(
                job_directory,
                "applying",
                team_1_summary=first.summary,
                team_2_summary=second.summary,
            )
            self._logger.fire("Applying reviewed patch", **context)
            apply_patch(self._project, second.patch_path.read_bytes())
            self._write_status(
                job_directory,
                "completed",
                team_1_summary=first.summary,
                team_2_summary=second.summary,
                final_patch=str(second.patch_path),
            )
            self._logger.fire("Pipeline completed", **context)
        except Exception as error:
            self._logger.fire(
                "Pipeline failed",
                "error",
                **context,
                error=str(error),
            )
            self._write_status(job_directory, "failed", error=str(error))
            raise

    @staticmethod
    def _write_status(job_directory: Path, state: str, **details: str) -> None:
        path = job_directory / "status.json"
        temporary = path.with_suffix(f".json.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps({"state": state, **details}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
