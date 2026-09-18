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
    assert "would conflict; nothing was merged" in ctx.err.getvalue()
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


def test_conflict_message_names_the_conflicting_file(make_ctx):
    ctx, fake, repo, _ = reviewed(make_ctx)
    write(repo / "README.md", "branch\n")
    git(repo, "commit", "--quiet", "-am", "branch readme")
    git(repo, "checkout", "--quiet", "development")
    write(repo / "README.md", "development\n")
    git(repo, "commit", "--quiet", "-am", "development readme")

    assert main(["finish", "Q-010"], ctx) == 1

    assert "README.md" in ctx.err.getvalue()


def second_repo(workspace, name="q_contracts"):
    origin = workspace.parent / f"{name}-origin.git"
    repo = workspace / name
    git(workspace, "init", "--quiet", "--bare", str(origin))
    git(workspace, "clone", "--quiet", str(origin), str(repo))
    write(repo / "README.md", f"# {name}\n")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "init")
    git(repo, "push", "--quiet", "origin", "HEAD:main")
    git(repo, "checkout", "--quiet", "-b", "development")
    git(repo, "push", "--quiet", "-u", "origin", "development")
    return repo


def branch_commit(repo, workdir=None, name="contract.txt"):
    workdir = workdir or repo
    if workdir == repo:
        git(repo, "checkout", "--quiet", "-b", BRANCH)
    write(workdir / name, "change\n")
    git(workdir, "add", name)
    git(workdir, "commit", "--quiet", "-m", "change")
    if workdir == repo:
        git(repo, "checkout", "--quiet", "development")


def test_finish_merges_every_repository_with_the_task_branch(make_ctx):
    ctx, fake, repo, _ = reviewed(make_ctx)
    contracts = second_repo(ctx.workspace)
    branch_commit(contracts)
    untouched = second_repo(ctx.workspace, "q_frontend")
    untouched_head = git(untouched, "rev-parse", "development")

    assert main(["finish", "Q-010", "--push"], ctx) == 0

    for r in (repo, contracts):
        assert git(r, "branch", "--show-current").strip() == "development"
        assert len(git(r, "rev-list", "--parents", "-n1", "HEAD").split()) == 3
        git(r, "fetch", "--quiet", "origin")
        assert git(r, "rev-parse", "origin/development") == git(r, "rev-parse", "development")
    assert (contracts / "contract.txt").exists()
    assert git(untouched, "rev-parse", "development") == untouched_head
    [close] = fake.gh("gh", "issue", "close")
    assert "q_contracts as" in close[-1] and "q_backend as" in close[-1]
    assert fake.status_edits() == [("PVTI_Q-010", "Done")]


def test_finish_removes_secondary_worktree(make_ctx):
    ctx, fake, repo, _ = reviewed(make_ctx)
    contracts = second_repo(ctx.workspace)
    git(contracts, "branch", BRANCH, "development")
    wt = ctx.workspace / ".worktrees/q_contracts" / BRANCH
    wt.parent.mkdir(parents=True)
    git(contracts, "worktree", "add", "--quiet", str(wt), BRANCH)
    branch_commit(contracts, wt)

    assert main(["finish", "Q-010"], ctx) == 0

    assert not wt.exists()
    assert (contracts / "contract.txt").exists()


def test_conflict_in_secondary_repository_merges_nothing(make_ctx):
    ctx, fake, repo, _ = reviewed(make_ctx)
    contracts = second_repo(ctx.workspace)
    branch_commit(contracts, name="README.md")
    write(contracts / "README.md", "development\n")
    git(contracts, "commit", "--quiet", "-am", "development readme")
    backend_head = git(repo, "rev-parse", "development")

    assert main(["finish", "Q-010"], ctx) == 1

    err = ctx.err.getvalue()
    assert "in q_contracts would conflict" in err and "README.md" in err
    assert git(repo, "rev-parse", "development") == backend_head
    assert fake.status_edits() == []
    assert git(contracts, "status", "--porcelain") == ""


def test_dirty_secondary_repository_is_refused(make_ctx):
    ctx, fake, repo, _ = reviewed(make_ctx)
    contracts = second_repo(ctx.workspace)
    branch_commit(contracts)
    write(contracts / "README.md", "dirty\n")

    assert main(["finish", "Q-010"], ctx) == 1

    assert "q_contracts has uncommitted changes" in ctx.err.getvalue()
    assert fake.status_edits() == []
