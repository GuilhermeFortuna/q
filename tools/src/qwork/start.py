"""`work start`: check a task can start, prepare its branch, launch an agent."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from qwork.agents import AGENTS, build_command
from qwork.board import DONE, IN_PROGRESS, TODO
from qwork.context import Context
from qwork.errors import QworkError
from qwork.repo import Git, task_files, worktree_path
from qwork.runner import CommandError
from qwork.template import render


def _warn_if_behind(ctx: Context, git: Git) -> None:
    try:
        git.fetch("origin", "development")
        behind = git.commits_behind("development", "origin/development")
    except CommandError as exc:
        print(f"work: warning: could not compare development with origin: {exc.stderr.strip()}", file=ctx.err)
        return
    if behind:
        print(f"work: warning: local development is {behind} commit(s) behind origin/development", file=ctx.err)


def start(
    ctx: Context,
    task_id: str,
    agent: str,
    effort: str | None,
    model: str | None,
    worktree: bool,
    dry_run: bool,
) -> int:
    board = ctx.board

    def rel(path: Path) -> str:
        return str(path.relative_to(ctx.workspace))

    task = board.task(task_id)
    if task.status not in (TODO, IN_PROGRESS):
        raise QworkError(f"{task.id} is '{task.status}'; only '{TODO}' or '{IN_PROGRESS}' tasks can be started")
    resuming = task.status == IN_PROGRESS

    unfinished = [dep for dep in (board.task(d) for d in task.depends_on) if dep.status != DONE]
    if unfinished:
        listed = ", ".join(f"{dep.id} ({dep.status})" for dep in unfinished)
        raise QworkError(f"{task.id} depends on unfinished tasks: {listed}")

    files = task_files(ctx.workspace, task)
    executable = AGENTS[agent].executable
    if ctx.which(executable) is None:
        raise QworkError(f"agent '{agent}' needs '{executable}' on PATH")

    git = Git(files.repo, ctx.run)
    branch_exists = git.branch_exists(task.branch)
    if branch_exists and not resuming:
        raise QworkError(
            f"{task.id} is '{TODO}' but branch {task.branch} already exists in {task.repo}; delete or rename it first"
        )

    wt = worktree_path(ctx.workspace, task)
    if worktree:
        workdir = wt
        if wt.exists() and Git(wt, ctx.run).current_branch() != task.branch:
            raise QworkError(f"{rel(wt)} exists but is not on {task.branch}")
    else:
        workdir = files.repo
        if git.is_dirty():
            raise QworkError(f"{task.repo} has uncommitted changes; commit or stash them, or use --worktree")

    _warn_if_behind(ctx, git)

    resume_note = (
        f"\n**Resuming:** `{task.branch}` already has work from an earlier session. Review "
        f"`git log development..{task.branch}` and the plan's checkboxes, then continue.\n"
        if resuming
        else ""
    )
    prompt = render(
        "implement",
        {
            "id": task.id,
            "title": task.title,
            "repo": task.repo,
            "issue_url": task.issue_url,
            "spec": rel(files.spec),
            "plan": rel(files.plan),
            "workdir": rel(workdir),
            "branch": task.branch,
            "resume": resume_note,
            "repo_agents": ", ".join(f"`{rel(p)}`" for p in files.instructions) or "none",
        },
    )
    launch = build_command(agent, prompt, effort, model)
    if launch.notice:
        print(f"work: {launch.notice}", file=ctx.err)

    if dry_run:
        actions = []
        if not branch_exists:
            actions.append(f"create branch {task.branch} from development in {task.repo}")
        if worktree:
            if not wt.exists():
                actions.append(f"add worktree {rel(wt)}")
        else:
            actions.append(f"check out {task.branch} in {task.repo}")
        if not resuming:
            actions.append(f"set {task.id} to '{IN_PROGRESS}'")
        actions.append(f"launch: {shlex.join(launch.argv[:-1])} <prompt>")
        print("Dry run — no changes made. Would:", file=ctx.out)
        for action in actions:
            print(f"  - {action}", file=ctx.out)
        print(f"\n--- prompt ---\n{prompt}", file=ctx.out)
        return 0

    if not branch_exists:
        git.create_branch(task.branch, "development")
    if worktree:
        if not wt.exists():
            git.add_worktree(wt, task.branch)
    else:
        git.checkout(task.branch)
    if not resuming:
        board.set_status(task, IN_PROGRESS)

    print(f"work: {task.id} on {task.branch} in {rel(workdir)}; launching {agent}", file=ctx.err)
    os.chdir(ctx.workspace)
    ctx.execvp(launch.argv[0], launch.argv)
    return 0
