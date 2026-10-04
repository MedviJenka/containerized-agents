from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_IGNORED_NAMES = {
    ".git",
    ".idea",
    ".omp-pipeline",
    ".pytest_cache",
    ".venv",
    "__pycache__",
}


def _run_git(
    workspace: Path,
    *args: str,
    input_data: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(workspace), *args],
        input=input_data,
        capture_output=True,
        check=True,
    )


def prepare_workspace(project: Path, workspace: Path) -> None:
    """Copy the current project state and commit it as an immutable baseline."""
    project = project.resolve()
    workspace = workspace.resolve()
    if workspace == project or project in workspace.parents:
        raise ValueError("workspace must not be the project or a project child")

    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(
        project,
        workspace,
        ignore=shutil.ignore_patterns(*_IGNORED_NAMES),
    )

    _run_git(workspace, "init", "--quiet")
    _run_git(workspace, "config", "user.name", "OMP Agent")
    _run_git(workspace, "config", "user.email", "omp-agent@localhost")
    _run_git(workspace, "add", "-A")
    _run_git(workspace, "commit", "--quiet", "--allow-empty", "-m", "Agent baseline")


def create_patch(workspace: Path) -> bytes:
    """Return every tracked, untracked, deleted, and binary workspace change."""
    _run_git(workspace, "add", "--intent-to-add", "--all")
    return _run_git(
        workspace,
        "diff",
        "--binary",
        "--full-index",
        "HEAD",
        "--",
    ).stdout


def apply_patch(workspace: Path, patch: bytes) -> None:
    """Check and atomically apply a Git patch to a workspace."""
    if not patch.strip():
        return
    _run_git(workspace, "apply", "--check", "--whitespace=nowarn", "-", input_data=patch)
    _run_git(workspace, "apply", "--whitespace=nowarn", "-", input_data=patch)
