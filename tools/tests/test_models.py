import pytest
from helpers import write

from qwork.cli import main


@pytest.fixture
def ctx(make_ctx, workspace):
    write(workspace / "docs/models.md", "# Agent models\n")
    ctx, _ = make_ctx([])
    return ctx


def test_document_launches_agent_scoped_to_missing_profiles(ctx):
    assert main(["models", "document", "--agent", "claude", "--model", "opus", "--effort", "high"], ctx) == 0
    [argv] = ctx.execvp.calls
    assert argv[-6:-1] == ["claude", "--model", "opus", "--effort", "high"]
    assert "Profile only the roster models that have no section" in argv[-1]
    assert "Do not commit" in argv[-1]


def test_refresh_scopes_agent_to_the_whole_roster(ctx):
    assert main(["models", "refresh", "--agent", "codex"], ctx) == 0
    [argv] = ctx.execvp.calls
    assert "Research every roster model again" in argv[-1]


def test_dry_run_prints_prompt_without_launching(ctx):
    assert main(["models", "refresh", "--agent", "claude", "--dry-run"], ctx) == 0
    assert ctx.execvp.calls == []
    assert "--- prompt ---" in ctx.out.getvalue()


def test_missing_models_file_fails(make_ctx):
    ctx, _ = make_ctx([])
    assert main(["models", "document", "--agent", "claude"], ctx) == 1
    assert "docs/models.md not found" in ctx.err.getvalue()
    assert ctx.execvp.calls == []
