from helpers import git, item, write
from qwork.cli import main

BRANCH = "Q-010-transactional-outbox"


def reviewed(make_ctx, *, worktree=False):
    ctx, fake = make_ctx([item("Q-010", "Transactional outbox", "In Review")])
    repo = ctx.workspace / "q_backend"
    git(repo, "branch", BRANCH, "development")
    workdir = repo
    if worktree:
        workdir = ctx.workspace / ".worktrees/q_backend" / BRANCH
        workdir.parent.mkdir(parents=True)
        git(repo, "worktree", "add", "--quiet", str(workdir), BRANCH)
    else:
        git(repo, "checkout", "--quiet", BRANCH)
    write(workdir / "feature.txt", "feature\n")
    git(workdir, "add", "feature.txt")
    git(workdir, "commit", "--quiet", "-m", "feature")
    return ctx, fake, repo, workdir


def test_finish_merges_keeps_branch_and_marks_done(make_ctx):
    ctx, fake, repo, _ = reviewed(make_ctx)
    origin_before = git(repo, "rev-parse", "origin/development").strip()
    assert main(["finish", "Q-010"], ctx) == 0
    assert git(repo, "branch", "--show-current").strip() == "development"
    assert len(git(repo, "rev-list", "--parents", "-n1", "HEAD").split()) == 3
    assert git(repo, "branch", "--list", BRANCH).strip() != ""
    sha = git(repo, "rev-parse", "HEAD").strip()
    assert fake.status_edits() == [("PVTI_Q-010", "Done")]
    [close] = fake.gh("gh", "issue", "close")
    assert sha in close[-1]
    git(repo, "fetch", "--quiet", "origin")
    assert git(repo, "rev-parse", "origin/development").strip() == origin_before


def test_finish_push(make_ctx):
    ctx, fake, repo, _ = reviewed(make_ctx)
    assert main(["finish", "Q-010", "--push"], ctx) == 0
    git(repo, "fetch", "--quiet", "origin")
    assert git(repo, "rev-parse", "origin/development") == git(repo, "rev-parse", "development")


def test_finish_removes_worktree_but_keeps_branch(make_ctx):
    ctx, fake, repo, workdir = reviewed(make_ctx, worktree=True)
    assert main(["finish", "Q-010"], ctx) == 0
    assert not workdir.exists()
    assert git(repo, "branch", "--list", BRANCH).strip() != ""
    assert (repo / "feature.txt").exists()


def test_conflict_aborts_without_board_changes(make_ctx):
    ctx, fake, repo, _ = reviewed(make_ctx)
    write(repo / "README.md", "branch\n")
    git(repo, "commit", "--quiet", "-am", "branch readme")
    git(repo, "checkout", "--quiet", "development")
    write(repo / "README.md", "development\n")
    git(repo, "commit", "--quiet", "-am", "development readme")
    assert main(["finish", "Q-010"], ctx) == 1
    assert "failed and was aborted" in ctx.err.getvalue()
    assert fake.status_edits() == []
    assert fake.gh("gh", "issue", "close") == []
    assert git(repo, "status", "--porcelain") == ""


def test_finish_requires_in_review(make_ctx):
    ctx, fake = make_ctx([item("Q-010", "Transactional outbox", "In Progress")])
    assert main(["finish", "Q-010"], ctx) == 1
    assert "is 'In Progress'" in ctx.err.getvalue()


def test_finish_requires_branch(make_ctx):
    ctx, fake = make_ctx([item("Q-010", "Transactional outbox", "In Review")])
    assert main(["finish", "Q-010"], ctx) == 1
    assert f"branch {BRANCH} does not exist" in ctx.err.getvalue()


def test_finish_refuses_worktree_with_untracked_files(make_ctx):
    ctx, fake, repo, workdir = reviewed(make_ctx, worktree=True)
    write(workdir / "scratch.txt", "x")
    assert main(["finish", "Q-010"], ctx) == 1
    assert "uncommitted or untracked" in ctx.err.getvalue()
    assert fake.status_edits() == []
