"""Review workflow against real Git repositories; only GitHub is faked."""

import json
import subprocess
import sys

import pytest

from helpers import git, item, write
from qwork.cli import main
from qwork.runner import CommandError
from test_finish import BRANCH, reviewed, second_repo


def journal(ctx):
    return ctx.workspace / ".worktrees/inspect.json"


def branch(path):
    return git(path, "branch", "--show-current").strip()


def head(path):
    return git(path, "rev-parse", "HEAD").strip()


def test_inspect_detaches_worktree_and_restores_offline(make_ctx):
    ctx, fake, repo, wt = reviewed(make_ctx, worktree=True)
    original = head(repo)
    tip = head(wt)
    assert main(["inspect", "Q-010"], ctx) == 0
    assert branch(repo) == BRANCH
    assert (repo / "feature.txt").read_text() == "feature\n"
    assert branch(wt) == "" and head(wt) == tip
    assert journal(ctx).exists()
    assert fake.status_edits() == []
    assert fake.gh("gh", "issue", "comment") == []

    # Restore must work even when GitHub is unavailable.
    def offline(*args):
        raise AssertionError("restore accessed GitHub")

    ctx.board.task = offline
    assert main(["inspect", "--restore"], ctx) == 0
    assert branch(repo) == "development" and head(repo) == original
    assert branch(wt) == BRANCH and head(wt) == tip
    assert not journal(ctx).exists()


def test_multi_repo_mixed_modes_and_untouched_repo(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    contracts = second_repo(ctx.workspace)
    git(contracts, "branch", BRANCH)
    untouched = second_repo(ctx.workspace, "q_frontend")
    write(untouched / "scratch.txt", "unrelated work")
    assert main(["inspect", "Q-010"], ctx) == 0
    assert branch(contracts) == branch(repo) == BRANCH
    assert branch(untouched) == "development"
    assert main(["inspect", "--restore"], ctx) == 0
    assert branch(contracts) == branch(repo) == "development"
    assert branch(wt) == BRANCH
    assert (untouched / "scratch.txt").exists()


@pytest.mark.parametrize("where,tracked", [("repo", True), ("repo", False), ("wt", True), ("wt", False)])
def test_dirty_checkout_refuses_before_any_switch(make_ctx, where, tracked):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    path = repo if where == "repo" else wt
    write(path / ("README.md" if tracked else "scratch.txt"), "dirty")
    assert main(["inspect", "Q-010"], ctx) == 1
    assert "uncommitted or untracked" in ctx.err.getvalue()
    assert branch(repo) == "development" and branch(wt) == BRANCH
    assert not journal(ctx).exists()


def test_secondary_preflight_changes_nothing(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    other = second_repo(ctx.workspace, "q_terminal")
    git(other, "branch", BRANCH)
    write(other / "scratch.txt", "dirty")
    assert main(["inspect", "Q-010"], ctx) == 1
    assert branch(repo) == "development" and branch(wt) == BRANCH


@pytest.mark.parametrize("status", ["Todo", "In Progress", "Blocked", "Done"])
def test_only_in_review_tasks(make_ctx, status):
    ctx, _ = make_ctx([item("Q-010", "Transactional outbox", status)])
    assert main(["inspect", "Q-010"], ctx) == 1
    assert "In Review" in ctx.err.getvalue()
    assert not journal(ctx).exists()


def test_missing_branch(make_ctx):
    ctx, _ = make_ctx([item("Q-010", "Transactional outbox", "In Review")])
    assert main(["inspect", "Q-010"], ctx) == 1
    assert "does not exist" in ctx.err.getvalue()


def test_dry_run_does_not_create_state(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    assert main(["inspect", "Q-010", "--dry-run"], ctx) == 0
    assert branch(repo) == "development" and branch(wt) == BRANCH
    assert not journal(ctx).exists()
    assert "q_backend" in ctx.out.getvalue()


def test_repeated_inspection_keeps_original_state(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    assert main(["inspect", "Q-010"], ctx) == 0
    saved = journal(ctx).read_text()
    assert main(["inspect", "Q-010"], ctx) == 0
    assert journal(ctx).read_text() == saved
    assert main(["inspect", "Q-011"], ctx) == 1
    assert main(["inspect", "--restore"], ctx) == 0
    assert branch(repo) == "development" and branch(wt) == BRANCH


def test_detached_starting_checkout(make_ctx):
    ctx, _, repo, _ = reviewed(make_ctx)
    git(repo, "checkout", "--quiet", "--detach", "development")
    original = head(repo)
    assert main(["inspect", "Q-010"], ctx) == 0
    assert main(["inspect", "--restore"], ctx) == 0
    assert branch(repo) == "" and head(repo) == original


def test_already_on_task_branch(make_ctx):
    ctx, _, repo, _ = reviewed(make_ctx)
    assert main(["inspect", "Q-010"], ctx) == 0
    assert main(["inspect", "--restore"], ctx) == 0
    assert branch(repo) == BRANCH


def test_task_branch_in_other_worktree_is_refused(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    other = ctx.workspace / "other"
    git(repo, "worktree", "move", str(wt), str(other))
    assert main(["inspect", "Q-010"], ctx) == 1
    assert branch(repo) == "development" and branch(other) == BRANCH


def test_registered_missing_worktree_is_refused(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    wt.rename(wt.with_name("missing"))
    assert main(["inspect", "Q-010"], ctx) == 1
    assert branch(repo) == "development"


def test_wrong_branch_in_expected_worktree_is_refused(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    git(wt, "checkout", "--quiet", "-b", "other")
    assert main(["inspect", "Q-010"], ctx) == 1
    assert branch(repo) == "development" and branch(wt) == "other"


def test_restore_preserves_review_commits(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    assert main(["inspect", "Q-010"], ctx) == 0
    write(repo / "review.txt", "fix")
    git(repo, "add", "review.txt")
    git(repo, "commit", "--quiet", "-m", "review fix")
    tip = head(repo)
    assert main(["inspect", "--restore"], ctx) == 0
    assert branch(wt) == BRANCH and head(wt) == tip
    assert (wt / "review.txt").read_text() == "fix"


@pytest.mark.parametrize("change", ["dirty", "branch", "detached_commit"])
def test_restore_refuses_unexpected_changes_without_switching(make_ctx, change):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    assert main(["inspect", "Q-010"], ctx) == 0
    if change == "dirty":
        write(repo / "scratch.txt", "dirty")
    elif change == "branch":
        git(repo, "checkout", "--quiet", "-b", "unexpected")
    else:
        write(wt / "commit.txt", "keep me")
        git(wt, "add", "commit.txt")
        git(wt, "commit", "--quiet", "-m", "detached work")
    before = head(wt)
    assert main(["inspect", "--restore"], ctx) == 1
    assert branch(repo) == ("unexpected" if change == "branch" else BRANCH)
    assert head(wt) == before and journal(ctx).exists()


def test_switch_failure_rolls_back(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    run = ctx.run

    def fail(args, cwd=None):
        if args[:3] == ["git", "checkout", "--quiet"] and args[-1] == BRANCH and cwd == repo:
            raise CommandError(args, 1, "injected failure")
        return run(args, cwd)

    ctx.run = fail
    assert main(["inspect", "Q-010"], ctx) == 1
    assert branch(repo) == "development" and branch(wt) == BRANCH
    assert not journal(ctx).exists()


def test_interrupted_switch_can_restore(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    run = ctx.run

    def interrupt(args, cwd=None):
        result = run(args, cwd)
        if args[:4] == ["git", "checkout", "--quiet", "--detach"]:
            raise KeyboardInterrupt
        return result

    ctx.run = interrupt
    with pytest.raises(KeyboardInterrupt):
        main(["inspect", "Q-010"], ctx)
    assert journal(ctx).exists() and branch(wt) == ""
    ctx.run = run
    assert main(["inspect", "--restore"], ctx) == 0
    assert branch(repo) == "development" and branch(wt) == BRANCH


def test_inspect_then_finish_clears_state(make_ctx):
    ctx, fake, repo, wt = reviewed(make_ctx, worktree=True)
    assert main(["inspect", "Q-010"], ctx) == 0
    assert main(["finish", "Q-010"], ctx) == 0
    assert branch(repo) == "development" and not wt.exists()
    assert (repo / "feature.txt").exists() and not journal(ctx).exists()
    assert fake.status_edits() == [("PVTI_Q-010", "Done")]


def test_finish_other_task_refused(make_ctx):
    ctx, _, repo, _ = reviewed(make_ctx, worktree=True)
    assert main(["inspect", "Q-010"], ctx) == 0
    assert main(["finish", "Q-011"], ctx) == 1
    assert branch(repo) == BRANCH and journal(ctx).exists()


def test_failed_finish_retains_retry_state(make_ctx):
    ctx, fake, repo, wt = reviewed(make_ctx, worktree=True)
    assert main(["inspect", "Q-010"], ctx) == 0
    run = ctx.run

    def fail(args, cwd=None):
        if args[:2] == ["git", "push"]:
            raise CommandError(args, 1, "push unavailable")
        return run(args, cwd)

    ctx.run = fail
    assert main(["finish", "Q-010", "--push"], ctx) == 1
    assert branch(repo) == "development" and not wt.exists()
    assert journal(ctx).exists() and fake.status_edits() == []
    assert main(["inspect", "--restore"], ctx) == 1
    ctx.run = run
    assert main(["finish", "Q-010"], ctx) == 0
    assert not journal(ctx).exists()


def root_reviewed(make_ctx):
    ctx, _ = make_ctx([item("Q-070", "Unified development launcher", "In Review", repo="q")])
    ws = ctx.workspace
    git(ws, "init", "--quiet")
    write(ws / ".gitignore", "/q_backend/\n/.worktrees/\n")
    write(ws / "README.md", "workspace\n")
    git(ws, "add", "README.md", ".gitignore")
    git(ws, "commit", "--quiet", "-m", "init")
    git(ws, "branch", "-M", "development")
    task_branch = "Q-070-unified-development-launcher"
    git(ws, "branch", task_branch)
    wt = ws / ".worktrees/q" / task_branch
    git(ws, "worktree", "add", "--quiet", str(wt), task_branch)
    return ctx, ws, wt, task_branch


def test_workspace_owned_task_has_source_independent_recovery(make_ctx):
    ctx, ws, wt, task_branch = root_reviewed(make_ctx)
    assert main(["inspect", "Q-070"], ctx) == 0
    assert branch(ws) == task_branch and branch(wt) == ""
    # This fixture's selected root branch has no ./work or tools at all.
    runner = ws / ".worktrees/inspect-runner/work"
    assert runner.is_file()
    result = subprocess.run([sys.executable, str(runner), "inspect", "--restore"],
                            cwd=ws.parent, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert branch(ws) == "development" and branch(wt) == task_branch
    assert not runner.parent.exists() and not journal(ctx).exists()


def test_failed_journal_removal_preserves_recovery_runner(make_ctx, monkeypatch):
    from pathlib import Path

    ctx, ws, wt, task_branch = root_reviewed(make_ctx)
    assert main(["inspect", "Q-070"], ctx) == 0
    unlink = Path.unlink

    def fail(path, *args, **kwargs):
        if path == journal(ctx):
            raise PermissionError("cannot remove journal")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail)
    assert main(["inspect", "--restore"], ctx) == 1
    assert journal(ctx).exists()
    assert (ws / ".worktrees/inspect-runner/work").is_file()
    monkeypatch.setattr(Path, "unlink", unlink)
    assert main(["inspect", "--restore"], ctx) == 0
    assert branch(ws) == "development" and branch(wt) == task_branch


def test_corrupt_journal_reports_error(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    journal(ctx).write_text(json.dumps({"version": 999}))
    assert main(["inspect", "--restore"], ctx) == 1
    assert branch(repo) == "development" and branch(wt) == BRANCH


def test_ignored_environment_survives_switches(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    exclude = repo / ".git/info/exclude"
    with exclude.open("a") as stream:
        stream.write("\n.env\n")
    write(repo / ".env", "local configuration")
    write(wt / ".env", "worktree configuration")
    assert main(["inspect", "Q-010"], ctx) == 0
    assert main(["inspect", "--restore"], ctx) == 0
    assert (repo / ".env").read_text() == "local configuration"
    assert (wt / ".env").read_text() == "worktree configuration"


def test_interrupted_restore_can_resume(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    assert main(["inspect", "Q-010"], ctx) == 0
    run = ctx.run

    def interrupt(args, cwd=None):
        result = run(args, cwd)
        if cwd == repo and args[:3] == ["git", "checkout", "--quiet"] and args[-1] == "development":
            raise KeyboardInterrupt
        return result

    ctx.run = interrupt
    with pytest.raises(KeyboardInterrupt):
        main(["inspect", "--restore"], ctx)
    assert branch(repo) == "development" and branch(wt) == ""
    ctx.run = run
    assert main(["inspect", "--restore"], ctx) == 0
    assert branch(wt) == BRANCH and not journal(ctx).exists()


def test_restore_preflights_original_branch_held_elsewhere(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    assert main(["inspect", "Q-010"], ctx) == 0
    other = ctx.workspace / "other"
    git(repo, "worktree", "add", "--quiet", str(other), "development")
    assert main(["inspect", "--restore"], ctx) == 1
    assert branch(repo) == BRANCH and branch(wt) == ""
    assert journal(ctx).exists()


def test_inspect_and_finish_are_serialized(make_ctx):
    import fcntl

    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    path = ctx.workspace / ".worktrees/inspect.lock"
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert main(["inspect", "Q-010"], ctx) == 1
        assert main(["finish", "Q-010"], ctx) == 1
        assert "another inspect" in ctx.err.getvalue()
    assert branch(repo) == "development" and branch(wt) == BRANCH


def test_failed_finish_retry_preserves_new_detached_commits(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    assert main(["inspect", "Q-010"], ctx) == 0
    run = ctx.run

    def fail(args, cwd=None):
        if args[:3] == ["git", "worktree", "remove"]:
            raise CommandError(args, 1, "remove unavailable")
        return run(args, cwd)

    ctx.run = fail
    assert main(["finish", "Q-010"], ctx) == 1
    ctx.run = run
    write(wt / "keep.txt", "detached work")
    git(wt, "add", "keep.txt")
    git(wt, "commit", "--quiet", "-m", "detached work")
    assert main(["finish", "Q-010"], ctx) == 1
    assert (wt / "keep.txt").exists() and journal(ctx).exists()


def test_finish_retries_after_board_update_succeeded(make_ctx):
    from qwork.board import Board
    from helpers import FakeRunner

    ctx, _, repo, _ = reviewed(make_ctx, worktree=True)
    assert main(["inspect", "Q-010"], ctx) == 0
    def unavailable(*args):
        raise CommandError(["gh", "issue", "close"], 1, "GitHub unavailable")

    ctx.board.close = unavailable
    assert main(["finish", "Q-010"], ctx) == 1
    assert journal(ctx).exists()
    ctx.board = Board(FakeRunner([item("Q-010", "Transactional outbox", "Done")]))
    assert main(["finish", "Q-010"], ctx) == 0
    assert not journal(ctx).exists() and branch(repo) == "development"


def test_changed_repository_set_requires_restore(make_ctx):
    ctx, _, repo, _ = reviewed(make_ctx, worktree=True)
    assert main(["inspect", "Q-010"], ctx) == 0
    other = second_repo(ctx.workspace, "q_terminal")
    git(other, "branch", BRANCH)
    assert main(["finish", "Q-010"], ctx) == 1
    assert branch(repo) == BRANCH and branch(other) == "development"


def test_inspect_never_overwrites_ignored_environment(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    with (repo / ".git/info/exclude").open("a") as stream:
        stream.write("\n.env\n")
    write(wt / ".env", "tracked task configuration")
    git(wt, "add", "--force", ".env")
    git(wt, "commit", "--quiet", "-m", "track configuration")
    write(repo / ".env", "private original configuration")
    assert main(["inspect", "Q-010"], ctx) == 1
    assert (repo / ".env").read_text() == "private original configuration"
    assert branch(repo) == "development" and branch(wt) == BRANCH
    assert not journal(ctx).exists()


def test_restore_never_overwrites_ignored_environment(make_ctx):
    ctx, _, repo, wt = reviewed(make_ctx, worktree=True)
    with (repo / ".git/info/exclude").open("a") as stream:
        stream.write("\n.env\n")
    write(repo / ".env", "tracked base configuration")
    git(repo, "add", "--force", ".env")
    git(repo, "commit", "--quiet", "-m", "base configuration")
    assert main(["inspect", "Q-010"], ctx) == 0
    write(repo / ".env", "private review configuration")
    assert main(["inspect", "--restore"], ctx) == 1
    assert (repo / ".env").read_text() == "private review configuration"
    assert branch(repo) == BRANCH and branch(wt) == ""
    assert journal(ctx).exists()


def test_workspace_root_can_be_secondary_participant(make_ctx):
    ctx, _, repo, _ = reviewed(make_ctx, worktree=True)
    ws = ctx.workspace
    git(ws, "init", "--quiet")
    write(ws / ".gitignore", "/q_backend/\n/.worktrees/\n")
    write(ws / "README.md", "workspace\n")
    git(ws, "add", "README.md", ".gitignore")
    git(ws, "commit", "--quiet", "-m", "init")
    git(ws, "branch", "-M", "development")
    git(ws, "checkout", "--quiet", "-b", BRANCH)
    write(ws / "feature.txt", "workspace change")
    git(ws, "add", "feature.txt")
    git(ws, "commit", "--quiet", "-m", "workspace change")
    git(ws, "checkout", "--quiet", "development")
    assert main(["inspect", "Q-010"], ctx) == 0
    assert branch(ws) == branch(repo) == BRANCH
    assert main(["finish", "Q-010"], ctx) == 0
    assert branch(ws) == branch(repo) == "development"
    assert (ws / "feature.txt").read_text() == "workspace change"
