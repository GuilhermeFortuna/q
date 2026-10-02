"""`work finish`: merge a reviewed task into development and mark it Done.

A task is owned by one repository but may also change others (a backend task
that recaptures a contract, for example). Every workspace repository that has
the task branch is merged, so no repository's `development` is left behind.
"""

from __future__ import annotations

from qwork.board import DONE, IN_REVIEW
from qwork.context import Context
from qwork.errors import QworkError
from qwork.inspection import check_active, clear_session, load_session, save_session, workspace_lock
from qwork.release import is_release_repo, release
from qwork.repo import Git
from qwork.targets import Target, task_targets


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
    with workspace_lock(ctx):
        session = load_session(ctx)
        if session and session["task_id"] != task_id:
            raise QworkError(f"already inspecting {session['task_id']}; run `work inspect --restore` first")
        if session and session["phase"] != "finishing":
            check_active(ctx, session)
        try:
            return _finish(ctx, task_id, push, no_push, session)
        except QworkError as exc:
            if session and session["phase"] == "finishing":
                raise QworkError(f"{exc}; inspection state retained; resolve the failure and retry "
                                 f"`work finish {task_id}` (restore cannot undo merges)") from None
            raise


def _inspection_preflight(ctx: Context, task, targets: list[Target], session: dict) -> None:
    saved = {entry["name"]: entry for entry in session["targets"]}
    if session["branch"] != task.branch or set(saved) != {t.name for t in targets}:
        raise QworkError("task branch or involved repositories changed since inspection; restore before continuing")
    if session["phase"] != "finishing":
        return
    for target in targets:
        if target.git.current_branch() not in (task.branch, "development"):
            raise QworkError(f"{target.path} moved unexpectedly during finish")
        if target.git.is_dirty(include_untracked=True):
            raise QworkError(f"{target.path} has uncommitted or untracked files")
        entry = saved[target.name]
        records = {tree.path: tree for tree in target.git.worktrees()}
        tree = records.get(target.worktree.resolve())
        if tree or target.worktree.exists():
            expected = entry["worktree_before"]
            if expected is None or tree is None or not target.worktree.is_dir() or tree.unavailable:
                raise QworkError(f"{target.worktree} is missing or changed during finish")
            if tree.branch or tree.head != expected["head"]:
                raise QworkError(f"{target.worktree} moved unexpectedly; preserve detached commits before retrying")
        if task.status == DONE and not target.git.is_ancestor(task.branch, "development"):
            raise QworkError(f"{task.branch} is not merged in {target.name}; cannot complete GitHub recovery")


def _finish(ctx: Context, task_id: str, push: bool, no_push: bool, session: dict | None) -> int:
    task = ctx.board.task(task_id)
    completed_on_board = bool(session and session["phase"] == "finishing" and task.status == DONE)
    if task.status != IN_REVIEW and not completed_on_board:
        raise QworkError(f"{task.id} is '{task.status}'; only '{IN_REVIEW}' tasks can be finished")

    targets = task_targets(ctx, task)
    if session:
        _inspection_preflight(ctx, task, targets, session)
    _preflight(ctx, task, targets)

    if session:
        session["phase"] = "finishing"
        save_session(ctx, session)

    merged: list[tuple[Target, str]] = []
    for t in targets:
        t.git.checkout("development", preserve_ignored=True)
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

    if not completed_on_board:
        ctx.board.set_status(task, DONE)
    pushed = " and pushed" if pushing else " (not pushed)"
    where = ", ".join(f"{t.name} as {sha}" for t, sha in merged)
    released = "".join(f" Released {name} as `{tag}`." for name, tag in tags.items())
    ctx.board.close(task, f"Merged `{task.branch}` into `development` in {where}{pushed}.{released}")
    if session:
        clear_session(ctx)
    summary = ", ".join(f"{t.name} ({sha[:10]})" for t, sha in merged)
    tagged = "".join(f", tagged {name} {tag}" for name, tag in tags.items())
    print(f"{task.id}: merged {task.branch} into development in {summary}{pushed}{tagged}; marked {DONE}", file=ctx.out)
    return 0
