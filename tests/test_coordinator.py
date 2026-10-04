import json
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import MagicMock, call


from agent_service.coordinator import PipelineCoordinator
from agent_service.worker import AgentWorker, RunRequest, WorkerSettings


class EditingRpc:
    def __init__(self, workspace: Path, text: str) -> None:
        self.workspace = workspace
        self.text = text

    def run(self, prompt: str) -> str:
        (self.workspace / "result.txt").write_text(self.text, encoding="utf-8")
        return self.text


class LocalWorkerClient:
    def __init__(self, worker: AgentWorker) -> None:
        self.worker = worker

    def run(self, request: RunRequest):
        return self.worker.run(request)


class CoordinatorTests(unittest.TestCase):
    def test_runs_both_stages_then_applies_reviewed_patch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            shared = root / "shared"
            project.mkdir()
            shared.mkdir()
            (project / "result.txt").write_text("base", encoding="utf-8")

            first_workspace = root / "first"
            first_logger = MagicMock()
            second_logger = MagicMock()
            coordinator_logger = MagicMock()

            second_workspace = root / "second"
            first = AgentWorker(
                WorkerSettings("team_1", project, first_workspace, shared),
                EditingRpc(first_workspace, "implemented"),
                first_logger,
            )
            second = AgentWorker(
                WorkerSettings("team_2", project, second_workspace, shared),
                EditingRpc(second_workspace, "reviewed"),
                second_logger,
            )
            coordinator = PipelineCoordinator(
                project,
                shared,
                LocalWorkerClient(first),
                LocalWorkerClient(second),
                coordinator_logger,
            )
            job_id = uuid4()
            request = RunRequest(job_id=job_id, prompt="Implement it")

            coordinator.queue(request)
            coordinator.run(request)

            self.assertEqual((project / "result.txt").read_text(encoding="utf-8"), "reviewed")
            status = json.loads(
                (shared / "jobs" / str(job_id) / "status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["state"], "completed")
            coordinator_logger.log.assert_has_calls(
                [
                    call("Job queued", job_id=str(job_id)),
                    call("Pipeline started", job_id=str(job_id)),
                    call("Team 1 started", job_id=str(job_id)),
                    call("Team 1 completed", job_id=str(job_id)),
                    call("Team 2 started", job_id=str(job_id)),
                    call("Team 2 completed", job_id=str(job_id)),
                    call("Applying reviewed patch", job_id=str(job_id)),
                    call("Pipeline completed", job_id=str(job_id)),
                ]
            )

    def test_logs_pipeline_failure_with_job_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            shared = root / "shared"
            project.mkdir()
            shared.mkdir()
            team_1 = MagicMock()
            team_1.run.side_effect = RuntimeError("agent failed")
            logger = MagicMock()
            coordinator = PipelineCoordinator(
                project,
                shared,
                team_1,
                MagicMock(),
                logger,
            )
            request = RunRequest(job_id=uuid4(), prompt="Implement it")

            with self.assertRaisesRegex(RuntimeError, "agent failed"):
                coordinator.run(request)

            logger.log.assert_called_with(
                "Pipeline failed",
                "error",
                job_id=str(request.job_id),
                error="agent failed",
            )
            status = json.loads(
                (
                    shared / "jobs" / str(request.job_id) / "status.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(status["state"], "failed")


if __name__ == "__main__":
    unittest.main()
