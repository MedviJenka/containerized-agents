from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import UUID

from agent_service.workspace import apply_patch, create_patch, prepare_workspace

if TYPE_CHECKING:
    from functions.log import Logger

Stage = Literal["team_1", "team_2"]


class RpcRunner(Protocol):
    def run(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class WorkerSettings:
    stage: Stage
    project: Path
    workspace: Path
    shared: Path


@dataclass(frozen=True)
class RunRequest:
    job_id: UUID
    prompt: str


@dataclass(frozen=True)
class RunResult:
    job_id: UUID
    stage: Stage
    summary: str
    patch_path: Path


class AgentWorker:
    def __init__(
        self,
        settings: WorkerSettings,
        rpc: RpcRunner,
        logger: Logger,
    ) -> None:
        self._settings = settings
        self._rpc = rpc
        self._logger = logger

    def run(self, request: RunRequest) -> RunResult:
        settings = self._settings
        context = {"job_id": str(request.job_id), "stage": settings.stage}
        self._logger.fire("Worker run started", **context)
        try:
            if not request.prompt.strip():
                raise ValueError("prompt must not be empty")

            prepare_workspace(settings.project, settings.workspace)
            self._logger.fire("Workspace prepared", **context)
            job_directory = settings.shared / "jobs" / str(request.job_id)
            job_directory.mkdir(parents=True, exist_ok=True)

            if settings.stage == "team_2":
                first_patch = job_directory / "team_1.patch"
                if not first_patch.is_file():
                    raise FileNotFoundError(
                        f"First-stage patch is missing: {first_patch}"
                    )
                apply_patch(settings.workspace, first_patch.read_bytes())
                self._logger.fire(
                    "First-stage patch applied",
                    **context,
                    patch_path=str(first_patch),
                )

            self._logger.fire("Agent run started", **context)
            summary = self._rpc.run(self._prompt(request.prompt))
            self._logger.fire("Agent run completed", **context)
            patch_path = job_directory / f"{settings.stage}.patch"
            self._atomic_write(patch_path, create_patch(settings.workspace))
            self._logger.fire(
                "Patch created",
                **context,
                patch_path=str(patch_path),
            )
            return RunResult(request.job_id, settings.stage, summary, patch_path)
        except Exception as error:
            self._logger.fire(
                "Worker run failed",
                "error",
                **context,
                error=str(error),
            )
            raise

    def _prompt(self, request: str) -> str:
        if self._settings.stage == "team_1":
            role = (
                "Implement the requested change in the current workspace. "
                "Inspect existing conventions, edit the actual files, and run focused verification."
            )
        else:
            role = (
                "Review the first team's implementation already applied to this workspace. "
                "Find correctness, security, and maintainability problems; fix every confirmed issue; "
                "then run focused verification."
            )
        return (
            f"{role}\n\n"
            f"User request:\n{request}\n\n"
            "Do not ask interactive questions. Do not commit. Leave the completed changes in the workspace."
        )

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
