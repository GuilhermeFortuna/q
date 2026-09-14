import io

import pytest

from helpers import STATUS_OPTIONS, FakeRunner, RecordingExec, git, write
from qwork.board import Board
from qwork.context import Context


@pytest.fixture(autouse=True)
def isolated_git(tmp_path_factory, monkeypatch):
    config = tmp_path_factory.mktemp("gitconfig") / "config"
    config.write_text("[user]\n\tname = Test\n\temail = test@example.com\n[init]\n\tdefaultBranch = main\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "q"
    origin = tmp_path / "origin.git"
    repo = ws / "q_backend"
    ws.mkdir()
    git(tmp_path, "init", "--quiet", "--bare", str(origin))
    git(tmp_path, "clone", "--quiet", str(origin), str(repo))
    write(repo / "README.md", "# q_backend\n")
    write(repo / "docs/development/specs/Q-010-transactional-outbox-spec.md", "# Q-010 spec\n")
    write(repo / "docs/development/plans/Q-010-transactional-outbox-plan.md", "# Q-010 plan\n")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "init")
    git(repo, "push", "--quiet", "origin", "HEAD:main")
    git(repo, "checkout", "--quiet", "-b", "development")
    git(repo, "push", "--quiet", "-u", "origin", "development")
    return ws


@pytest.fixture
def make_ctx(workspace, monkeypatch):
    monkeypatch.chdir(workspace)

    def factory(items, status_options=STATUS_OPTIONS):
        fake = FakeRunner(items, status_options)
        ctx = Context(
            workspace=workspace,
            board=Board(fake),
            run=fake,
            out=io.StringIO(),
            err=io.StringIO(),
            execvp=RecordingExec(),
            which=lambda name: f"/usr/bin/{name}",
        )
        return ctx, fake

    return factory
