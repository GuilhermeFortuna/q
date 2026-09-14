"""`work board show` and `work board set`."""

from __future__ import annotations

from qwork.board import check_agent_transition
from qwork.context import Context
from qwork.errors import QworkError
from qwork.repo import Git, task_files, worktree_path


def board_show(ctx: Context, task_id: str) -> int:
    task = ctx.board.task(task_id)
    deps = ", ".join(f"{dep} ({ctx.board.task(dep).status})" for dep in task.depends_on) or "none"
    lines = [
        f"{task.id}  {task.status}",
        task.title,
        f"issue:    {task.issue_url}",
        f"repo:     {task.repo}",
        f"depends:  {deps}",
    ]
    try:
        files = task_files(ctx.workspace, task)
    except QworkError as exc:
        lines += [f"branch:   {task.branch}", f"files:    {exc}"]
    else:
        exists = Git(files.repo, ctx.run).branch_exists(task.branch)
        worktree = worktree_path(ctx.workspace, task)
        lines += [
            f"spec:     {files.spec.relative_to(ctx.workspace)}",
            f"plan:     {files.plan.relative_to(ctx.workspace)}",
            f"branch:   {task.branch} ({'exists' if exists else 'not created'})",
            f"worktree: {worktree.relative_to(ctx.workspace) if worktree.exists() else 'none'}",
        ]
    print("\n".join(lines), file=ctx.out)
    return 0


def board_set(ctx: Context, task_id: str, target: str, message: str | None) -> int:
    task = ctx.board.task(task_id)
    status = check_agent_transition(task, target, message)
    ctx.board.set_status(task, status)
    if message:
        ctx.board.comment(task, message)
    print(f"{task.id}: {task.status} -> {status}", file=ctx.out)
    return 0
