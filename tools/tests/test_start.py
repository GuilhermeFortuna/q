import os

from helpers import git, item, write
from qwork.cli import main

BRANCH = "Q-010-transactional-outbox"


def q010(status="Todo", depends=None):
    return item("Q-010", "Transactional outbox", status, depends=depends)


def test_start_todo_in_branch_mode(make_ctx):
    ctx, fake = make_ctx([q010()])
    assert main(["start", "Q-010", "--agent", "claude"], ctx) == 0
    repo = ctx.workspace / "q_backend"
    assert git(repo, "branch", "--show-current").strip() == BRANCH
    assert fake.status_edits() == [("PVTI_Q-010", "In Progress")]
    [argv] = ctx.execvp.calls
    assert argv[:3] == ["claude", "--effort", "medium"]
    assert "q_backend/docs/development/plans/Q-010-transactional-outbox-plan.md" in argv[-1]
    assert "Working directory: `q_backend`" in argv[-1]
    assert "Resuming" not in argv[-1]
    assert os.getcwd() == str(ctx.workspace)


def test_dry_run_changes_nothing(make_ctx):
    ctx, fake = make_ctx([q010()])
    assert main(["start", "Q-010", "--agent", "codex", "--effort", "high", "--dry-run"], ctx) == 0
    repo = ctx.workspace / "q_backend"
    assert git(repo, "branch", "--list", BRANCH) == ""
    assert fake.status_edits() == []
    assert ctx.execvp.calls == []
    out = ctx.out.getvalue()
    assert "Dry run" in out
    assert f"create branch {BRANCH} from development" in out
    assert "launch: codex -m gpt-5.6-terra -c model_reasoning_effort=high <prompt>" in out
    assert f"{ctx.workspace}/work board set Q-010 in-review" in out
    assert f"relative to the workspace root `{ctx.workspace}`" in out


def test_start_with_worktree(make_ctx):
    ctx, fake = make_ctx([q010()])
    assert main(["start", "Q-010", "--agent", "antigravity", "--worktree"], ctx) == 0
    path = ctx.workspace / ".worktrees/q_backend" / BRANCH
    assert git(path, "branch", "--show-current").strip() == BRANCH
    assert git(ctx.workspace / "q_backend", "branch", "--show-current").strip() == "development"
    [argv] = ctx.execvp.calls
    assert argv[0] == "agy"
    assert f"Working directory: `.worktrees/q_backend/{BRANCH}`" in argv[-1]


def test_unfinished_dependency_blocks_start(make_ctx):
    ctx, fake = make_ctx([q010(depends="Q-009"), item("Q-009", "Payload", "In Review", repo="q_contracts")])
    assert main(["start", "Q-010", "--agent", "claude"], ctx) == 1
    assert "depends on unfinished tasks: Q-009 (In Review)" in ctx.err.getvalue()
    assert fake.status_edits() == []
    assert ctx.execvp.calls == []


def test_only_todo_or_in_progress_can_start(make_ctx):
    for status in ("Blocked", "In Review", "Done"):
        ctx, fake = make_ctx([q010(status)])
        assert main(["start", "Q-010", "--agent", "claude"], ctx) == 1
        assert f"is '{status}'" in ctx.err.getvalue()


def test_existing_branch_on_todo_task_is_refused(make_ctx):
    ctx, fake = make_ctx([q010()])
    git(ctx.workspace / "q_backend", "branch", BRANCH)
    assert main(["start", "Q-010", "--agent", "claude"], ctx) == 1
    assert "already exists" in ctx.err.getvalue()
    assert fake.status_edits() == []


def test_resume_in_progress_reuses_branch(make_ctx):
    ctx, fake = make_ctx([q010("In Progress")])
    git(ctx.workspace / "q_backend", "branch", BRANCH)
    assert main(["start", "Q-010", "--agent", "claude"], ctx) == 0
    assert fake.status_edits() == []
    [argv] = ctx.execvp.calls
    assert "Resuming" in argv[-1]


def test_dirty_checkout_is_refused_in_branch_mode(make_ctx):
    ctx, fake = make_ctx([q010()])
    write(ctx.workspace / "q_backend/README.md", "edited\n")
    assert main(["start", "Q-010", "--agent", "claude"], ctx) == 1
    assert "uncommitted changes" in ctx.err.getvalue()
    assert ctx.execvp.calls == []


def test_missing_agent_executable_is_refused(make_ctx):
    ctx, fake = make_ctx([q010()])
    ctx.which = lambda name: None
    assert main(["start", "Q-010", "--agent", "cursor"], ctx) == 1
    assert "needs 'agent' on PATH" in ctx.err.getvalue()


def test_invalid_effort_is_refused_before_changes(make_ctx):
    ctx, fake = make_ctx([q010()])
    assert main(["start", "Q-010", "--agent", "antigravity", "--effort", "max"], ctx) == 1
    assert "does not support effort 'max'" in ctx.err.getvalue()
    assert git(ctx.workspace / "q_backend", "branch", "--list", BRANCH) == ""


def test_launch_env_strips_qwork_venv(make_ctx, monkeypatch):
    ctx, fake = make_ctx([q010()])
    monkeypatch.setenv("VIRTUAL_ENV", "/opt/q/tools/.venv")
    monkeypatch.setenv("QWORK_WORKSPACE", "/opt/q")
    monkeypatch.setenv("PATH", "/opt/q/tools/.venv/bin:/usr/bin:/bin")
    monkeypatch.setenv("KEEP_ME", "yes")
    assert main(["start", "Q-010", "--agent", "claude"], ctx) == 0
    [env] = ctx.execvp.envs
    assert "VIRTUAL_ENV" not in env
    assert "QWORK_WORKSPACE" not in env
    assert "/opt/q/tools/.venv/bin" not in env["PATH"].split(os.pathsep)
    assert "/usr/bin" in env["PATH"].split(os.pathsep)
    assert env["KEEP_ME"] == "yes"


def test_launch_env_untouched_without_virtualenv(make_ctx, monkeypatch):
    ctx, fake = make_ctx([q010()])
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert main(["start", "Q-010", "--agent", "claude"], ctx) == 0
    [env] = ctx.execvp.envs
    assert env["PATH"] == "/usr/bin:/bin"


def test_exec_failure_is_reported_as_one_line(make_ctx):
    ctx, fake = make_ctx([q010()])

    def boom(argv0, argv, env):
        raise OSError(2, "No such file or directory")

    ctx.execvp = boom
    assert main(["start", "Q-010", "--agent", "claude"], ctx) == 1
    err = ctx.err.getvalue()
    assert "Traceback" not in err
    assert "work: failed to launch" in err


def test_warns_when_development_is_behind_origin(make_ctx):
    ctx, fake = make_ctx([q010()])
    repo = ctx.workspace / "q_backend"
    write(repo / "a.txt", "a")
    git(repo, "add", "a.txt")
    git(repo, "commit", "--quiet", "-m", "a")
    git(repo, "push", "--quiet", "origin", "development")
    git(repo, "reset", "--quiet", "--hard", "HEAD~1")
    assert main(["start", "Q-010", "--agent", "claude", "--dry-run"], ctx) == 0
    assert "1 commit(s) behind origin/development" in ctx.err.getvalue()
