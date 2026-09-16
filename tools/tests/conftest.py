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
            stream=fake,
        )
        return ctx, fake

    return factory


@pytest.fixture
def release_repo(workspace):
    """A q_core-like repository: RELEASING.md plus Cargo and pyproject versions."""
    origin = workspace.parent / "q_core-origin.git"
    repo = workspace / "q_core"
    git(workspace, "init", "--quiet", "--bare", str(origin))
    git(workspace, "clone", "--quiet", str(origin), str(repo))
    write(repo / "RELEASING.md", "# Releasing q_core\n")
    write(repo / "Cargo.toml", '[workspace.package]\nversion = "2026.9.1"\nedition = "2021"\n')
    write(repo / "pyproject.toml", '[project]\nname = "q-core"\nversion = "2026.9.1"\n')
    write(repo / "docs/development/specs/Q-029-tick-kernel-spec.md", "# Q-029 spec\n")
    write(repo / "docs/development/plans/Q-029-tick-kernel-plan.md", "# Q-029 plan\n")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "init")
    git(repo, "push", "--quiet", "origin", "HEAD:main")
    git(repo, "checkout", "--quiet", "-b", "development")
    git(repo, "push", "--quiet", "-u", "origin", "development")
    return repo
