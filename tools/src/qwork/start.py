"""`work start`: check a task can start, prepare its branch, launch an agent."""

from __future__ import annotations

import json
import os
import shlex
from collections.abc import Mapping
from pathlib import Path

from qwork.agents import AGENTS, build_command
from qwork.board import DONE, IN_PROGRESS, TODO
from qwork.confine import build_env, confine
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


def _launch_env(env: Mapping[str, str]) -> dict[str, str]:
    """A copy of `env` safe to launch an agent with: no qwork venv or workspace marker."""
    clean = dict(env)
    venv = clean.pop("VIRTUAL_ENV", None)
    clean.pop("QWORK_WORKSPACE", None)
    if venv:
        venv_bin = str(Path(venv) / "bin")
        parts = [p for p in clean.get("PATH", "").split(os.pathsep) if p != venv_bin]
        clean["PATH"] = os.pathsep.join(parts)
    return clean


def _cargo_target_links(repo: Path, worktree: Path) -> list[tuple[Path, Path]]:
    """Mirror checkout Cargo target links with isolated storage per worktree."""
    links = []
    for relative in (Path("target"), Path("src-tauri/target")):
        checkout_target = repo / relative
        if not checkout_target.is_symlink():
            continue
        source = checkout_target.resolve()
        if not source.is_dir():
            raise QworkError(f"{checkout_target} points to a missing Cargo target directory")
        worktree_target = worktree / relative
        destination = source.parent / f"{source.name}-{worktree.name}"
        if worktree_target.is_symlink():
            if worktree_target.resolve() != destination:
                raise QworkError(f"{worktree_target} points to a different Cargo target directory")
        elif worktree_target.exists():
            raise QworkError(f"{worktree_target} already has a local Cargo target; move it before resuming")
        links.append((worktree_target, destination))
    return links


def _configure_cargo_target(repo: Path, worktree: Path, destination: Path) -> None:
    """Keep Cargo on external storage even if `cargo clean` removes target/ links."""
    config = worktree / ".cargo/config.toml"
    contents = f"[build]\ntarget-dir = {json.dumps(str(destination))}\n"
    if config.exists() and config.read_text() != contents:
        raise QworkError(f"{config} already configures Cargo differently")
    exclude = repo / ".git/info/exclude"
    pattern = "/.cargo/config.toml"
    existing = exclude.read_text() if exclude.exists() else ""
    if pattern not in existing.splitlines():
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a") as stream:
            stream.write(f"\n{pattern}\n")
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(contents)


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
        target_links = _cargo_target_links(files.repo, wt)
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
            "workspace": str(ctx.workspace),
        },
    )
    launch = build_command(agent, prompt, effort, model)
    if launch.notice:
        print(f"work: {launch.notice}", file=ctx.err)
    argv, confine_notice = confine(launch.argv, ctx.which)
    if confine_notice:
        print(f"work: warning: {confine_notice}", file=ctx.err)

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
        actions.append(f"launch: {shlex.join(argv[:-1])} <prompt>")
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
        for link, destination in target_links:
            destination.mkdir(parents=True, exist_ok=True)
            link.parent.mkdir(parents=True, exist_ok=True)
            if not link.is_symlink():
                link.symlink_to(destination, target_is_directory=True)
        if target_links:
            _configure_cargo_target(files.repo, wt, target_links[0][1])
    else:
        git.checkout(task.branch)
    if not resuming:
        board.set_status(task, IN_PROGRESS)

    print(f"work: {task.id} on {task.branch} in {rel(workdir)}; launching {agent}", file=ctx.err)
    os.chdir(ctx.workspace)
    env = build_env(_launch_env(os.environ))
    try:
        ctx.execvp(argv[0], argv, env)
    except OSError as exc:
        raise QworkError(f"failed to launch '{agent}': {exc}") from None
    return 0
