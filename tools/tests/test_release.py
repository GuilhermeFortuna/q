"""`work finish` cuts a release when the task's repository has a RELEASING.md."""

from __future__ import annotations

import datetime

from helpers import git, item, write
from qwork.cli import main

BRANCH = "Q-029-tick-kernel"


def today() -> datetime.date:
    return datetime.date.today()


def version() -> str:
    day = today()
    return f"{day.year}.{day.month}.{day.day}"


def tag() -> str:
    return f"v{today():%Y.%m.%d}"


def reviewed(make_ctx, release_repo, *, branch_version="2026.9.1"):
    ctx, fake = make_ctx([item("Q-029", "Tick kernel", "In Review", repo="q_core", number=7)])
    git(release_repo, "checkout", "--quiet", "-b", BRANCH)
    write(release_repo / "kernel.rs", "fn tick() {}\n")
    write(release_repo / "Cargo.toml", f'[workspace.package]\nversion = "{branch_version}"\nedition = "2021"\n')
    write(release_repo / "pyproject.toml", f'[project]\nname = "q-core"\nversion = "{branch_version}"\n')
    git(release_repo, "add", "-A")
    git(release_repo, "commit", "--quiet", "-m", "tick kernel")
    git(release_repo, "checkout", "--quiet", "development")
    return ctx, fake, release_repo


def test_finish_tags_and_pushes_the_release(make_ctx, release_repo):
    ctx, fake, repo = reviewed(make_ctx, release_repo)

    assert main(["finish", "Q-029"], ctx) == 0

    assert git(repo, "tag", "--list", tag()).strip() == tag()
    assert git(repo, "rev-parse", f"{tag()}^{{}}").strip() == git(repo, "rev-parse", "development").strip()
    assert git(repo, "ls-remote", "--tags", "origin", tag()).strip() != ""
    git(repo, "fetch", "--quiet", "origin")
    assert git(repo, "rev-parse", "origin/development") == git(repo, "rev-parse", "development")
    assert f'version = "{version()}"' in (repo / "Cargo.toml").read_text()
    assert f'version = "{version()}"' in (repo / "pyproject.toml").read_text()
    assert fake.ran("make", "check") != []
    assert fake.status_edits() == [("PVTI_Q-029", "Done")]


def test_failed_check_leaves_task_in_review_without_tag_or_push(make_ctx, release_repo):
    ctx, fake, repo = reviewed(make_ctx, release_repo)
    fake.failures.append(("make", "check"))
    origin_before = git(repo, "rev-parse", "origin/development").strip()

    assert main(["finish", "Q-029"], ctx) == 1

    assert "`make check` failed" in ctx.err.getvalue()
    assert git(repo, "tag", "--list").strip() == ""
    git(repo, "fetch", "--quiet", "origin")
    assert git(repo, "rev-parse", "origin/development").strip() == origin_before
    assert fake.status_edits() == []
    assert fake.gh("gh", "issue", "close") == []


def test_second_release_on_the_same_day_is_suffixed(make_ctx, release_repo):
    ctx, fake, repo = reviewed(make_ctx, release_repo)
    git(repo, "tag", tag())

    assert main(["finish", "Q-029"], ctx) == 0

    assert git(repo, "rev-parse", f"{tag()}.2^{{}}").strip() == git(repo, "rev-parse", "development").strip()
    assert git(repo, "ls-remote", "--tags", "origin", f"{tag()}.2").strip() != ""


def test_version_already_current_adds_no_bump_commit(make_ctx, release_repo):
    ctx, fake, repo = reviewed(make_ctx, release_repo, branch_version=version())

    assert main(["finish", "Q-029"], ctx) == 0

    assert "chore(release)" not in git(repo, "log", "--format=%s", "development")
    assert git(repo, "tag", "--list", tag()).strip() == tag()


def test_non_release_repo_is_untouched(make_ctx):
    from test_finish import reviewed as reviewed_backend

    ctx, fake, repo, _ = reviewed_backend(make_ctx)

    assert main(["finish", "Q-010"], ctx) == 0

    assert fake.ran("make") == []
    assert git(repo, "tag", "--list").strip() == ""


def test_no_push_tags_locally_without_touching_origin(make_ctx, release_repo):
    ctx, fake, repo = reviewed(make_ctx, release_repo)
    origin_before = git(repo, "rev-parse", "origin/development").strip()

    assert main(["finish", "Q-029", "--no-push"], ctx) == 0

    assert git(repo, "tag", "--list", tag()).strip() == tag()
    assert git(repo, "ls-remote", "--tags", "origin", tag()).strip() == ""
    git(repo, "fetch", "--quiet", "origin")
    assert git(repo, "rev-parse", "origin/development").strip() == origin_before
