"""`work finish`: merge a reviewed task into development and mark it Done.

A task is owned by one repository but may also change others (a backend task
that recaptures a contract, for example). Every workspace repository that has
the task branch is merged, so no repository's `development` is left behind.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qwork.board import DONE, IN_REVIEW
from qwork.context import Context
from qwork.errors import QworkError
from qwork.release import is_release_repo, release
from qwork.repo import Git, workspace_repos, worktree_path

# Producers merge first so consumers never land ahead of what they pin.
MERGE_ORDER = ("q_contracts", "q_core")


@dataclass
class Target:
    name: str
    path: Path
    git: Git
    worktree: Path


def _targets(ctx: Context, task) -> list[Target]:
    primary = ctx.workspace / task.repo
    if not primary.is_dir():
        raise QworkError(f"{task.id}: repository {task.repo} is not cloned at {primary}")
    if not Git(primary, ctx.run).branch_exists(task.branch):
        raise QworkError(f"branch {task.branch} does not exist in {task.repo}")

    targets = []
    for path in workspace_repos(ctx.workspace):
        git = Git(path, ctx.run)
        if path == primary or git.branch_exists(task.branch):
            targets.append(Target(path.name, path, git, worktree_path(ctx.workspace, task, path.name)))
    rank = {name: i for i, name in enumerate(MERGE_ORDER)}
    return sorted(targets, key=lambda t: (rank.get(t.name, len(rank)), t.name))


def _preflight(ctx: Context, task, targets: list[Target]) -> None:
    """Refuse before merging anything, so a task is never left half-merged."""
    for t in targets:
        if t.worktree.exists() and Git(t.worktree, ctx.run).is_dirty(include_untracked=True):
            raise QworkError(f"{t.worktree.relative_to(ctx.workspace)} has uncommitted or untracked files")
        if t.git.is_dirty():
            raise QworkError(f"{t.name} has uncommitted changes")
        conflicts = t.git.merge_conflicts("development", task.branch)
        if conflicts:
            listed = "\n".join(f"  {f}" for f in conflicts)
            raise QworkError(
                f"merging {task.branch} into development in {t.name} would conflict; nothing was merged in any "
                f"repository. Resolve it on {task.branch} and run `work finish {task.id}` again:\n{listed}"
            )


def finish(ctx: Context, task_id: str, push: bool, no_push: bool = False) -> int:
    task = ctx.board.task(task_id)
    if task.status != IN_REVIEW:
        raise QworkError(f"{task.id} is '{task.status}'; only '{IN_REVIEW}' tasks can be finished")

    targets = _targets(ctx, task)
    _preflight(ctx, task, targets)

    merged: list[tuple[Target, str]] = []
    for t in targets:
        t.git.checkout("development")
        merged.append((t, t.git.merge_no_ff(task.branch, f"Merge {task.branch} into development")))
        if t.worktree.exists():
            t.git.remove_worktree(t.worktree)

    tags: dict[str, str] = {}
    for t in targets:
        if is_release_repo(t.path):
            # A rerun after a failed check must not tag the same release twice.
            existing = [tag for tag in t.git.tags_at("HEAD") if tag.startswith("v")]
            tags[t.name] = existing[0] if existing else release(ctx, t.git, t.path, task)

    pushing = (push or bool(tags)) and not no_push
    if pushing:
        for t in targets:
            t.git.push("origin", "development")
            if t.name in tags:
                t.git.push_tag("origin", tags[t.name])

    ctx.board.set_status(task, DONE)
    pushed = " and pushed" if pushing else " (not pushed)"
    where = ", ".join(f"{t.name} as {sha}" for t, sha in merged)
    released = "".join(f" Released {name} as `{tag}`." for name, tag in tags.items())
    ctx.board.close(task, f"Merged `{task.branch}` into `development` in {where}{pushed}.{released}")
    summary = ", ".join(f"{t.name} ({sha[:10]})" for t, sha in merged)
    tagged = "".join(f", tagged {name} {tag}" for name, tag in tags.items())
    print(f"{task.id}: merged {task.branch} into development in {summary}{pushed}{tagged}; marked {DONE}", file=ctx.out)
    return 0
