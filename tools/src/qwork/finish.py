"""`work finish`: merge a reviewed task into development and mark it Done."""

from __future__ import annotations

from qwork.board import DONE, IN_REVIEW
from qwork.context import Context
from qwork.errors import QworkError
from qwork.release import is_release_repo, release
from qwork.repo import Git, worktree_path


def finish(ctx: Context, task_id: str, push: bool, no_push: bool = False) -> int:
    task = ctx.board.task(task_id)
    if task.status != IN_REVIEW:
        raise QworkError(f"{task.id} is '{task.status}'; only '{IN_REVIEW}' tasks can be finished")

    repo_path = ctx.workspace / task.repo
    if not repo_path.is_dir():
        raise QworkError(f"{task.id}: repository {task.repo} is not cloned at {repo_path}")
    git = Git(repo_path, ctx.run)
    if not git.branch_exists(task.branch):
        raise QworkError(f"branch {task.branch} does not exist in {task.repo}")

    wt = worktree_path(ctx.workspace, task)
    if wt.exists() and Git(wt, ctx.run).is_dirty(include_untracked=True):
        raise QworkError(f"{wt.relative_to(ctx.workspace)} has uncommitted or untracked files")
    if git.is_dirty():
        raise QworkError(f"{task.repo} has uncommitted changes")

    git.checkout("development")
    sha = git.merge_no_ff(task.branch, f"Merge {task.branch} into development")
    if wt.exists():
        git.remove_worktree(wt)

    tag = release(ctx, git, repo_path, task) if is_release_repo(repo_path) else None
    pushing = (push or tag is not None) and not no_push
    if pushing:
        git.push("origin", "development")
    if tag and pushing:
        git.push_tag("origin", tag)

    ctx.board.set_status(task, DONE)
    pushed = " and pushed" if pushing else " (not pushed)"
    released = f" Released as `{tag}`." if tag else ""
    ctx.board.close(task, f"Merged `{task.branch}` into `development` as {sha}{pushed}.{released}")
    tagged = f", tagged {tag}" if tag else ""
    print(f"{task.id}: merged {task.branch} into development ({sha[:10]}){pushed}{tagged}; marked {DONE}", file=ctx.out)
    return 0
