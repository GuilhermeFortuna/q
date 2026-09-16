"""Cut a dated release in a producer repository, as `RELEASING.md` describes.

A repository is a producer when it has a `RELEASING.md`: today only `q_core`,
whose consumers pin a tag rather than a branch. `work finish` calls `release`
after the merge so that a task reaching `Done` is one its consumers can pin.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from qwork.context import Context
from qwork.errors import QworkError
from qwork.repo import Git
from qwork.runner import CommandError

VERSION_RE = re.compile(r'^(version\s*=\s*")[^"]*(")', re.MULTILINE)
VERSION_FILES = ("Cargo.toml", "pyproject.toml")


def is_release_repo(repo: Path) -> bool:
    return (repo / "RELEASING.md").is_file()


def release_version(day: datetime.date) -> str:
    """The unpadded `YYYY.M.D` form used by Cargo and pyproject."""
    return f"{day.year}.{day.month}.{day.day}"


def tag_name(day: datetime.date, taken: set[str]) -> str:
    """`vYYYY.MM.DD`, suffixed `.n` when that day already has releases."""
    base = f"v{day:%Y.%m.%d}"
    if base not in taken:
        return base
    n = 2
    while f"{base}.{n}" in taken:
        n += 1
    return f"{base}.{n}"


def set_versions(repo: Path, version: str) -> list[str]:
    """Set every `version = "..."` in the version files; return those changed."""
    changed = []
    for name in VERSION_FILES:
        path = repo / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        updated = VERSION_RE.sub(rf'\g<1>{version}\g<2>', text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed.append(name)
    return changed


def release(ctx: Context, git: Git, repo: Path, task, day: datetime.date | None = None) -> str:
    """Bump, validate, and tag `development`. Returns the tag; raises if checks fail."""
    day = day or datetime.date.today()
    version = release_version(day)

    changed = set_versions(repo, version)
    if changed:
        git.commit_paths(changed, f"chore(release): bump version to {version}")
        try:
            ctx.run(["cargo", "metadata", "--format-version", "1"], cwd=repo)
        except CommandError:
            pass
        if git.is_dirty():
            git.commit_paths(["Cargo.lock"], f"chore(release): refresh Cargo.lock for {version}")

    print(f"{task.id}: running `make check` in {task.repo} before tagging", file=ctx.err)
    try:
        ctx.stream(["make", "check"], cwd=repo)
    except CommandError as exc:
        raise QworkError(
            f"`make check` failed in {task.repo} ({exc.returncode}); the merge is committed locally but "
            f"nothing was tagged or pushed. Fix it on development and run `work finish {task.id}` again."
        ) from None

    tag = tag_name(day, set(git.tags()))
    git.tag(tag, f"{task.id}: {task.title}")
    return tag
