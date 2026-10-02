"""Local, reversible checkout selection for human review.

Every transition is journaled before Git runs. Recovery compares actual Git
state with both sides of each transition, including a command that succeeded
just before the process was interrupted. No reset, force checkout, or stash is
used; unexpected changes are left for the user to resolve.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from qwork.board import IN_REVIEW, validate_task_id
from qwork.context import Context
from qwork.errors import QworkError
from qwork.repo import Git
from qwork.targets import task_targets


def journal_path(ctx: Context) -> Path:
    return ctx.workspace / ".worktrees/inspect.json"


def _prepare_recovery_runner(ctx: Context) -> Path:
    """Keep offline recovery available when selecting older workspace sources."""
    directory = ctx.workspace / ".worktrees/inspect-runner"
    if directory.is_symlink():
        raise QworkError(f"{directory} must not be a symlink")
    if directory.exists():
        # No session exists: this can only be an unfinished snapshot from a
        # previous interruption before the first journal write.
        shutil.rmtree(directory)
    directory.mkdir()
    shutil.copytree(Path(__file__).parent, directory / "qwork", ignore=shutil.ignore_patterns("__pycache__"))
    runner = directory / "work"
    runner.write_text(
        f"#!{Path(sys.executable).resolve()}\n"
        '"""Source-independent recovery for the active workspace inspection."""\n'
        "import os\nimport sys\nfrom pathlib import Path\n"
        'os.environ["QWORK_WORKSPACE"] = str(Path(__file__).resolve().parents[2])\n'
        "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
        "from qwork.cli import entry\nentry()\n"
    )
    runner.chmod(0o700)
    return runner


def clear_session(ctx: Context) -> None:
    journal_path(ctx).unlink()
    fd = os.open(journal_path(ctx).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    # Keep the recovery runner until journal removal is durable. If orphan
    # cleanup fails, the operation is still complete and no session remains.
    directory = ctx.workspace / ".worktrees/inspect-runner"
    if directory.is_dir() and not directory.is_symlink():
        try:
            shutil.rmtree(directory)
        except OSError as exc:
            print(f"work: warning: inspection completed, but remove unused {directory}: {exc}", file=ctx.err)


@contextmanager
def workspace_lock(ctx: Context, dry_run: bool = False):
    path = ctx.workspace / ".worktrees/inspect.lock"
    # A preview may use an existing lock, but must not create any files.
    if dry_run and not path.exists():
        yield
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = path.open("r" if dry_run else "a")
    except OSError as exc:
        raise QworkError(f"cannot access inspection lock: {exc}") from None
    with stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise QworkError("another inspect, restore, or finish operation is running") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _path(ctx: Context, relative: str) -> Path:
    path = ctx.workspace / relative
    if Path(relative).is_absolute() or path.resolve() != path.absolute() or ".." in Path(relative).parts:
        raise ValueError("invalid journal path")
    return path


def _valid_state(state: dict) -> None:
    if not isinstance(state["branch"], str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", state["head"]):
        raise ValueError("invalid checkout state")


def load_session(ctx: Context) -> dict | None:
    path = journal_path(ctx)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if data["version"] != 1 or data["phase"] not in ("preparing", "active", "restoring", "finishing"):
            raise ValueError("unsupported version or phase")
        validate_task_id(data["task_id"])
        if not isinstance(data["branch"], str) or not data["branch"].startswith(data["task_id"] + "-"):
            raise ValueError("invalid task branch")
        if not data["targets"]:
            raise ValueError("empty target list")
        allowed = set()
        for target in data["targets"]:
            _path(ctx, target["repo"])
            _valid_state(target["normal_before"])
            allowed.add(target["repo"])
            if target["worktree"] is not None:
                _path(ctx, target["worktree"])
                _valid_state(target["worktree_before"])
                allowed.add(target["worktree"])
        for op in data["operations"]:
            if op["path"] not in allowed:
                raise ValueError("operation outside target checkouts")
            _valid_state(op["before"])
            _valid_state(op["after"])
        return data
    except (OSError, ValueError, KeyError, TypeError, QworkError) as exc:
        raise QworkError(f"invalid inspection journal {path}: {exc}; preserve it for recovery") from None


def save_session(ctx: Context, data: dict) -> None:
    path = journal_path(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".inspect-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        # Persist the rename as well as the journal contents.
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _state(git: Git) -> dict:
    return {"branch": git.current_branch(), "head": git.head()}


def _matches(actual: dict, expected: dict) -> bool:
    # Commits made on a named branch remain reachable when switching away.
    return actual["branch"] == expected["branch"] and (
        bool(expected["branch"]) or actual["head"] == expected["head"]
    )


def _clean(git: Git) -> None:
    if git.is_dirty(include_untracked=True):
        raise QworkError(f"{git.path} has uncommitted or untracked files; commit or move them first")


def _registered(ctx: Context, target: dict) -> None:
    """Never let Git fall back to a parent repository for a missing worktree."""
    repo = _path(ctx, target["repo"])
    records = {tree.path: tree for tree in Git(repo, ctx.run).worktrees()}
    for relative in (target["repo"], target["worktree"]):
        if relative is None:
            continue
        path = _path(ctx, relative)
        if path not in records or not path.is_dir() or records[path].unavailable:
            raise QworkError(f"{path} is missing, locked, or not a usable registered worktree")


def _check_operations(ctx: Context, data: dict) -> None:
    for target in data["targets"]:
        _registered(ctx, target)
        for key in ("repo", "worktree"):
            if target[key] is None:
                continue
            git = Git(_path(ctx, target[key]), ctx.run)
            _clean(git)
            actual = _state(git)
            op = next((o for o in data["operations"] if o["path"] == target[key]), None)
            expected = target["normal_before" if key == "repo" else "worktree_before"]
            states = (op["before"], op["after"]) if op else (expected,)
            if not any(_matches(actual, state) for state in states):
                raise QworkError(f"{git.path} moved unexpectedly; preserve its changes before recovery")


def check_active(ctx: Context, data: dict) -> None:
    if data["phase"] != "active":
        command = f"work finish {data['task_id']}" if data["phase"] == "finishing" else "work inspect --restore"
        raise QworkError(f"inspection is {data['phase']}; run `{command}` to recover")
    for target in data["targets"]:
        _registered(ctx, target)
        normal = Git(_path(ctx, target["repo"]), ctx.run)
        _clean(normal)
        if normal.current_branch() != data["branch"]:
            raise QworkError(f"{normal.path} moved unexpectedly; expected {data['branch']}")
        if target["worktree"]:
            wt = Git(_path(ctx, target["worktree"]), ctx.run)
            _clean(wt)
            expected = {"branch": "", "head": target["worktree_before"]["head"]}
            if _state(wt) != expected:
                raise QworkError(f"{wt.path} moved unexpectedly; preserve detached commits before restoring")


def _checkout(ctx: Context, relative: str, state: dict) -> None:
    git = Git(_path(ctx, relative), ctx.run)
    if state["branch"]:
        git.checkout(state["branch"], preserve_ignored=True)
    else:
        git.detach(state["head"])


def _apply(ctx: Context, data: dict) -> None:
    for op in data["operations"]:
        actual = _state(Git(_path(ctx, op["path"]), ctx.run))
        if _matches(actual, op["after"]):
            continue
        if not _matches(actual, op["before"]):
            raise QworkError(f"{op['path']} moved unexpectedly during inspection")
        _checkout(ctx, op["path"], op["after"])


def _restore_plan(ctx: Context, data: dict) -> list[dict]:
    operations = []
    for target in data["targets"]:
        # Release the task branch in the normal checkout before reattaching it.
        for key, saved in (("repo", "normal_before"), ("worktree", "worktree_before")):
            relative = target[key]
            if relative is None:
                continue
            git = Git(_path(ctx, relative), ctx.run)
            before = _state(git)
            after = target[saved]
            if after["branch"]:
                after = {"branch": after["branch"], "head": git.head(f"refs/heads/{after['branch']}")}
                for tree in git.worktrees():
                    if tree.branch == after["branch"] and tree.path != git.path:
                        # The normal checkout will release this branch earlier.
                        normal_path = _path(ctx, target["repo"])
                        if not (key == "worktree" and tree.path == normal_path
                                and target["normal_before"]["branch"] != after["branch"]):
                            raise QworkError(f"{after['branch']} is now checked out at {tree.path}; restore refused")
            if not _matches(before, after):
                operations.append({"path": relative, "before": before, "after": after})
    return operations


def restore(ctx: Context, dry_run: bool = False) -> int:
    data = load_session(ctx)
    if data is None:
        raise QworkError("no active inspection to restore")
    if data["phase"] == "finishing":
        raise QworkError(f"finishing has started; retry `work finish {data['task_id']}`; restoration cannot undo merges")
    if data["phase"] == "active":
        check_active(ctx, data)
    else:
        _check_operations(ctx, data)
    if data["phase"] != "restoring":
        data["operations"] = _restore_plan(ctx, data)
        data["phase"] = "restoring"
    if dry_run:
        print(f"Dry run — would restore {data['task_id']} in: " + ", ".join(t["name"] for t in data["targets"]), file=ctx.out)
        return 0
    save_session(ctx, data)
    _apply(ctx, data)
    clear_session(ctx)
    print(f"{data['task_id']}: restored original checkouts and task worktrees", file=ctx.out)
    return 0


def inspect(ctx: Context, task_id: str | None, restore_requested: bool, dry_run: bool) -> int:
    if restore_requested == bool(task_id):
        raise QworkError("use `work inspect ID` or `work inspect --restore`, not both")
    with workspace_lock(ctx, dry_run):
        if restore_requested:
            return restore(ctx, dry_run)
        existing = load_session(ctx)
        if existing:
            if existing["task_id"] != task_id:
                raise QworkError(f"already inspecting {existing['task_id']}; run `work inspect --restore` first")
            check_active(ctx, existing)
            print(f"{task_id}: inspection already active", file=ctx.out)
            return 0

        task = ctx.board.task(task_id)
        if task.status != IN_REVIEW:
            raise QworkError(f"{task.id} is '{task.status}'; only '{IN_REVIEW}' tasks can be inspected")
        data = {"version": 1, "task_id": task.id, "branch": task.branch,
                "phase": "preparing", "targets": [], "operations": []}
        for target in task_targets(ctx, task):
            _clean(target.git)
            records = {tree.path: tree for tree in target.git.worktrees()}
            expected = target.worktree.resolve()
            for tree in records.values():
                if tree.branch == task.branch and tree.path not in (target.path, expected):
                    raise QworkError(f"{task.branch} is checked out at unexpected worktree {tree.path}")
            tree = records.get(expected)
            if target.worktree.exists() and tree is None:
                raise QworkError(f"{target.worktree} is not a registered task worktree")
            before = _state(target.git)
            entry = {"name": target.name, "repo": str(target.path.relative_to(ctx.workspace)),
                     "normal_before": before, "worktree": None, "worktree_before": None}
            tip = target.git.head(f"refs/heads/{task.branch}")
            if tree:
                if not expected.is_dir() or tree.unavailable:
                    raise QworkError(f"{expected} is missing, locked, or unavailable")
                wt = Git(expected, ctx.run)
                _clean(wt)
                wt_before = _state(wt)
                if tree.branch not in ("", task.branch) or tree.head != tip:
                    raise QworkError(f"{expected} is not on {task.branch} at its current tip")
                entry["worktree"] = str(expected.relative_to(ctx.workspace))
                entry["worktree_before"] = wt_before
                if tree.branch:
                    data["operations"].append({"path": entry["worktree"], "before": wt_before,
                                               "after": {"branch": "", "head": tree.head}})
            if before["branch"] != task.branch:
                data["operations"].append({"path": entry["repo"], "before": before,
                                           "after": {"branch": task.branch, "head": tip}})
            data["targets"].append(entry)
            _registered(ctx, entry)

        names = ", ".join(t["name"] for t in data["targets"])
        print("Stop running stacks with `./dev down` and close desktop UIs before switching sources.", file=ctx.out)
        if dry_run:
            print(f"Dry run — would select {task.branch} in: {names}; preserve task worktrees detached", file=ctx.out)
            return 0
        if any(t["repo"] == "." for t in data["targets"]):
            runner = _prepare_recovery_runner(ctx)
            print(f"Workspace sources will switch too. If ./work changes, use "
                  f"`{runner.relative_to(ctx.workspace)} inspect --restore` or "
                  f"`{runner.relative_to(ctx.workspace)} finish {task.id}`.", file=ctx.out)
        save_session(ctx, data)
        try:
            _apply(ctx, data)
            data["phase"] = "active"
            save_session(ctx, data)
        except (QworkError, OSError) as exc:
            try:
                restore(ctx)
            except (QworkError, OSError) as rollback:
                raise QworkError(f"inspection failed: {exc}; recovery also failed: {rollback}; run `work inspect --restore`") from None
            raise QworkError(f"inspection failed; original checkouts restored: {exc}") from None
        print(f"{task.id}: selected {task.branch} in {names}\n"
              f"Run `./dev live`, `./dev research`, or `./dev`. "
              f"After review: `./work inspect --restore` or `./work finish {task.id}`.", file=ctx.out)
        return 0
