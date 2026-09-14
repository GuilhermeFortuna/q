"""Local repository layout and git operations for a task."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qwork.board import Task
from qwork.errors import QworkError
from qwork.runner import CommandError, Runner, run

INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md", "README.md")


@dataclass(frozen=True)
class TaskFiles:
    repo: Path
    spec: Path
    plan: Path
    instructions: tuple[Path, ...]


def _single(directory: Path, pattern: str, kind: str, task_id: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if not matches:
        raise QworkError(f"{task_id}: no {kind} matching {directory / pattern}")
    if len(matches) > 1:
        raise QworkError(f"{task_id}: {len(matches)} {kind} files match {directory / pattern}")
    return matches[0]


def task_files(workspace: Path, task: Task) -> TaskFiles:
    repo = workspace / task.repo
    if not repo.is_dir():
        raise QworkError(f"{task.id}: repository {task.repo} is not cloned at {repo}")
    docs = repo / "docs" / "development"
    return TaskFiles(
        repo=repo,
        spec=_single(docs / "specs", f"{task.id}-*-spec.md", "spec", task.id),
        plan=_single(docs / "plans", f"{task.id}-*-plan.md", "plan", task.id),
        instructions=tuple(repo / name for name in INSTRUCTION_FILES if (repo / name).is_file()),
    )


def worktree_path(workspace: Path, task: Task) -> Path:
    return workspace / ".worktrees" / task.repo / task.branch


class Git:
    def __init__(self, path: Path, runner: Runner = run) -> None:
        self.path = path
        self._run = runner

    def _git(self, *args: str) -> str:
        return self._run(["git", *args], cwd=self.path)

    def branch_exists(self, name: str) -> bool:
        try:
            self._git("rev-parse", "--verify", "--quiet", f"refs/heads/{name}")
        except CommandError:
            return False
        return True

    def current_branch(self) -> str:
        return self._git("branch", "--show-current").strip()

    def is_dirty(self, include_untracked: bool = False) -> bool:
        mode = "normal" if include_untracked else "no"
        return bool(self._git("status", "--porcelain", f"--untracked-files={mode}").strip())

    def fetch(self, remote: str, branch: str) -> None:
        self._git("fetch", "--quiet", remote, branch)

    def commits_behind(self, local: str, upstream: str) -> int:
        return int(self._git("rev-list", "--count", f"{local}..{upstream}").strip())

    def create_branch(self, name: str, start: str) -> None:
        self._git("branch", name, start)

    def checkout(self, name: str) -> None:
        self._git("checkout", "--quiet", name)

    def add_worktree(self, path: Path, branch: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._git("worktree", "add", "--quiet", str(path), branch)

    def remove_worktree(self, path: Path) -> None:
        self._git("worktree", "remove", str(path))

    def merge_no_ff(self, branch: str, message: str) -> str:
        try:
            self._git("merge", "--no-ff", "-m", message, branch)
        except CommandError as exc:
            try:
                self._git("merge", "--abort")
            except CommandError:
                pass
            raise QworkError(f"merging {branch} failed and was aborted: {exc.stderr.strip()}") from None
        return self._git("rev-parse", "HEAD").strip()

    def push(self, remote: str, branch: str) -> None:
        self._git("push", "--quiet", remote, branch)
