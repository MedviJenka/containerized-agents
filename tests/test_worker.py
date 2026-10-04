import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import MagicMock, call


from agent_service.worker import AgentWorker, RunRequest, WorkerSettings
from agent_service.workspace import apply_patch, prepare_workspace


class EditingRpc:
    def __init__(self, workspace: Path, text: str) -> None:
        self.workspace = workspace
        self.text = text
        self.prompts: list[str] = []

    def run(self, prompt: str) -> str:
        self.prompts.append(prompt)
        (self.workspace / "result.txt").write_text(self.text, encoding="utf-8")
        return f"wrote {self.text}"


class WorkerTests(unittest.TestCase):
    def test_second_stage_builds_on_first_stage_patch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            shared = root / "shared"
            project.mkdir()
            shared.mkdir()
            (project / "result.txt").write_text("base", encoding="utf-8")
            job_id = uuid4()
            first_logger = MagicMock()


            first_workspace = root / "first"
            first = AgentWorker(
                WorkerSettings("team_1", project, first_workspace, shared),
                EditingRpc(first_workspace, "implemented"),
                first_logger,
            )
            first_request = RunRequest(job_id=job_id, prompt="Implement it")
            first_result = first.run(first_request)
            self.assertTrue(first_result.patch_path.is_file())
            first_logger.log.assert_has_calls(
                [
                    call(
                        "Worker run started",
                        job_id=str(job_id),
                        stage="team_1",
                    ),
                    call(
                        "Workspace prepared",
                        job_id=str(job_id),
                        stage="team_1",
                    ),
                    call(
                        "Agent run started",
                        job_id=str(job_id),
                        stage="team_1",
                    ),
                    call(
                        "Agent run completed",
                        job_id=str(job_id),
                        stage="team_1",
                    ),
                    call(
                        "Patch created",
                        job_id=str(job_id),
                        stage="team_1",
                        patch_path=str(first_result.patch_path),
                    ),
                ]
            )


            second_workspace = root / "second"
            second_rpc = EditingRpc(second_workspace, "reviewed")
            second_logger = MagicMock()

            second = AgentWorker(
                WorkerSettings("team_2", project, second_workspace, shared),
                second_rpc,
                second_logger,
            )
            second_result = second.run(RunRequest(job_id=job_id, prompt="Implement it"))

            target = root / "target"
            prepare_workspace(project, target)
            apply_patch(target, second_result.patch_path.read_bytes())
            self.assertEqual((target / "result.txt").read_text(encoding="utf-8"), "reviewed")
            self.assertIn("Review", second_rpc.prompts[0])
            second_logger.log.assert_any_call(
                "First-stage patch applied",
                job_id=str(job_id),
                stage="team_2",
                patch_path=str(shared / "jobs" / str(job_id) / "team_1.patch"),
            )


    def test_logs_worker_failure_with_job_and_stage_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            shared = root / "shared"
            project.mkdir()
            shared.mkdir()
            rpc = MagicMock()
            rpc.run.side_effect = RuntimeError("rpc failed")
            logger = MagicMock()
            worker = AgentWorker(
                WorkerSettings("team_1", project, root / "workspace", shared),
                rpc,
                logger,
            )
            request = RunRequest(job_id=uuid4(), prompt="Implement it")

            with self.assertRaisesRegex(RuntimeError, "rpc failed"):
                worker.run(request)

            logger.log.assert_called_with(
                "Worker run failed",
                "error",
                job_id=str(request.job_id),
                stage="team_1",
                error="rpc failed",
            )

if __name__ == "__main__":
    unittest.main()
