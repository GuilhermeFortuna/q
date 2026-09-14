import pytest

from helpers import FakeRunner, git, item, write
from qwork.board import Board
from qwork.errors import QworkError
from qwork.repo import Git, task_files, worktree_path

BRANCH = "Q-010-transactional-outbox"


def q010(status="Todo"):
    return Board(FakeRunner([item("Q-010", "Transactional outbox", status)])).task("Q-010")


def test_task_files_are_found(workspace):
    files = task_files(workspace, q010())
    repo = workspace / "q_backend"
    assert files.repo == repo
    assert files.spec == repo / "docs/development/specs/Q-010-transactional-outbox-spec.md"
    assert files.plan == repo / "docs/development/plans/Q-010-transactional-outbox-plan.md"
    assert files.instructions == (repo / "README.md",)


def test_missing_repository_is_an_error(workspace):
    task = Board(FakeRunner([item("Q-020", "X", "Todo", repo="q_nowhere")])).task("Q-020")
    with pytest.raises(QworkError, match="q_nowhere is not cloned"):
        task_files(workspace, task)


def test_missing_plan_is_an_error(workspace):
    (workspace / "q_backend/docs/development/plans/Q-010-transactional-outbox-plan.md").unlink()
    with pytest.raises(QworkError, match="no plan matching"):
        task_files(workspace, q010())


def test_ambiguous_spec_is_an_error(workspace):
    write(workspace / "q_backend/docs/development/specs/Q-010-other-spec.md", "x")
    with pytest.raises(QworkError, match="2 spec files match"):
        task_files(workspace, q010())


def test_worktree_path(workspace):
    assert worktree_path(workspace, q010()) == workspace / ".worktrees" / "q_backend" / BRANCH


def test_branch_create_checkout_and_current(workspace):
    repo = Git(workspace / "q_backend")
    assert not repo.branch_exists(BRANCH)
    repo.create_branch(BRANCH, "development")
    assert repo.branch_exists(BRANCH)
    repo.checkout(BRANCH)
    assert repo.current_branch() == BRANCH


def test_is_dirty_ignores_untracked_by_default(workspace):
    repo = Git(workspace / "q_backend")
    write(workspace / "q_backend/new.txt", "x")
    assert not repo.is_dirty()
    assert repo.is_dirty(include_untracked=True)
    write(workspace / "q_backend/README.md", "changed\n")
    assert repo.is_dirty()


def test_commits_behind_after_fetch(workspace):
    path = workspace / "q_backend"
    write(path / "a.txt", "a")
    git(path, "add", "a.txt")
    git(path, "commit", "--quiet", "-m", "a")
    git(path, "push", "--quiet", "origin", "development")
    git(path, "reset", "--quiet", "--hard", "HEAD~1")
    repo = Git(path)
    repo.fetch("origin", "development")
    assert repo.commits_behind("development", "origin/development") == 1


def test_worktree_add_and_remove(workspace):
    repo = Git(workspace / "q_backend")
    repo.create_branch(BRANCH, "development")
    path = workspace / ".worktrees/q_backend" / BRANCH
    repo.add_worktree(path, BRANCH)
    assert Git(path).current_branch() == BRANCH
    repo.remove_worktree(path)
    assert not path.exists()
    assert repo.branch_exists(BRANCH)


def test_merge_no_ff_creates_a_merge_commit(workspace):
    path = workspace / "q_backend"
    git(path, "checkout", "--quiet", "-b", BRANCH)
    write(path / "feature.txt", "feature")
    git(path, "add", "feature.txt")
    git(path, "commit", "--quiet", "-m", "feature")
    git(path, "checkout", "--quiet", "development")
    sha = Git(path).merge_no_ff(BRANCH, f"Merge {BRANCH}")
    assert git(path, "rev-parse", "HEAD").strip() == sha
    assert len(git(path, "rev-list", "--parents", "-n1", "HEAD").split()) == 3


def test_merge_conflict_is_aborted(workspace):
    path = workspace / "q_backend"
    git(path, "checkout", "--quiet", "-b", BRANCH)
    write(path / "README.md", "branch\n")
    git(path, "commit", "--quiet", "-am", "branch")
    git(path, "checkout", "--quiet", "development")
    write(path / "README.md", "development\n")
    git(path, "commit", "--quiet", "-am", "development")
    with pytest.raises(QworkError, match="failed and was aborted"):
        Git(path).merge_no_ff(BRANCH, "merge")
    assert not (path / ".git/MERGE_HEAD").exists()
    assert git(path, "status", "--porcelain") == ""
