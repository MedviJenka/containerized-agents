import tempfile
import unittest
from pathlib import Path

from agent_service.workspace import apply_patch, create_patch, prepare_workspace


class WorkspaceTests(unittest.TestCase):
    def test_patch_contains_only_agent_changes_and_applies_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            worker = root / "worker"
            target = root / "target"
            project.mkdir()
            (project / "existing.txt").write_text("before\n", encoding="utf-8")
            (project / ".git").mkdir()
            (project / ".git" / "host-only").write_text("ignored", encoding="utf-8")

            prepare_workspace(project, worker)
            self.assertFalse((worker / ".git" / "host-only").exists())
            (worker / "existing.txt").write_text("after\n", encoding="utf-8")
            (worker / "new.txt").write_text("new\n", encoding="utf-8")
            patch = create_patch(worker)

            prepare_workspace(project, target)
            apply_patch(target, patch)

            self.assertEqual((target / "existing.txt").read_text(encoding="utf-8"), "after\n")
            self.assertEqual((target / "new.txt").read_text(encoding="utf-8"), "new\n")

    def test_empty_patch_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            apply_patch(workspace, b"")


if __name__ == "__main__":
    unittest.main()
