"""Repositories participating in a task, shared by inspect and finish."""

from dataclasses import dataclass
from pathlib import Path

from qwork.board import Task
from qwork.context import Context
from qwork.errors import QworkError
from qwork.repo import Git, repo_path, workspace_repos, worktree_path

# Producers precede their consumers when finishing a task.
MERGE_ORDER = ("q_contracts", "q_core")


@dataclass
class Target:
    name: str
    path: Path
    git: Git
    worktree: Path


def task_targets(ctx: Context, task: Task) -> list[Target]:
    primary = repo_path(ctx.workspace, task.repo)
    if not primary.is_dir():
        raise QworkError(f"{task.id}: repository {task.repo} is not cloned at {primary}")
    if not Git(primary, ctx.run).branch_exists(task.branch):
        raise QworkError(f"branch {task.branch} does not exist in {task.repo}")

    paths = workspace_repos(ctx.workspace)
    if (ctx.workspace / ".git").exists() and ctx.workspace not in paths:
        paths.append(ctx.workspace)
    if primary not in paths:
        paths.append(primary)
    targets = [
        Target("q" if path == ctx.workspace else path.name, path, Git(path, ctx.run),
               worktree_path(ctx.workspace, task, "q" if path == ctx.workspace else path.name))
        for path in paths if path == primary or Git(path, ctx.run).branch_exists(task.branch)
    ]
    rank = {name: i for i, name in enumerate(MERGE_ORDER)}
    return sorted(targets, key=lambda t: (rank.get(t.name, len(rank)), t.name))
