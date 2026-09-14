# Workspace Meta-repo and Agent Task Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `q/` a tracked meta-repo with shared agent instructions, and add `./work`, a CLI that launches Claude Code, Codex, Cursor or Antigravity on a board task, keeps the GitHub Project status current, and merges approved work into `development`.

**Architecture:** A small stdlib-only Python package (`qwork`) in `q/tools/`, run through a bash shim `q/work` via `uv`. Every external call (`gh`, `git`) goes through one runner function, so board logic is unit-tested against canned `gh` JSON and git logic is tested against real temporary repositories. Commands: `start`, `finish`, `board show`, `board set`.

**Tech Stack:** Python ≥ 3.12 (stdlib: `argparse`, `subprocess`, `string.Template`, `dataclasses`), `uv`, `hatchling`, `pytest`, `gh` CLI, `git`.

**Spec:** `docs/development/specs/workspace-agent-launcher-spec.md`

## Global Constraints

- Workspace root is `q/` (`/home/gui/projects/q`); all paths in this plan are relative to it.
- Board: owner `GuilhermeFortuna`, project number `2`. Status options: `Blocked`, `Todo`, `In Progress`, `In Review`, `Done`.
- Task IDs match `^Q-\d{3}$`. Board item titles look like `Q-010 — Transactional outbox`.
- Spec files: `<repo>/docs/development/specs/<ID>-*-spec.md`; plans: `<repo>/docs/development/plans/<ID>-*-plan.md`.
- Branch name: `<ID>-<slug of title after the ID>`, created from local `development`.
- Worktrees live in `q/.worktrees/<repo>/<branch>`.
- Runtime dependencies: none beyond the Python stdlib. Dev dependency: `pytest`.
- Agents never push, merge, check out `development`, or close issues. `board set` only accepts `in-review` and `blocked`, only from `In Progress`.
- `finish` keeps task branches; it only removes worktrees.
- Effort default `medium`. claude `low medium high xhigh max`; codex `minimal low medium high xhigh`; cursor `low medium high xhigh max` (needs `--model`); antigravity `low medium high`.
- Module layout refines spec §2.1: `errors.py`, `context.py`, `commands.py` (board show/set), `start.py` and `finish.py` are split out of `cli.py` to keep files focused.
- Commits in `q/` end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## File Map

| File | Responsibility |
|---|---|
| `.gitignore`, `.ignore` | Hide sibling repos from git; re-include them for ripgrep search |
| `AGENTS.md`, `CLAUDE.md` | Workspace agent instructions (`CLAUDE.md` imports `AGENTS.md`) |
| `q-workspace/` | Serena symlink view (fixed links) |
| `README.md` | Board status table gains `In Review`; agent workflow section |
| `work` | Bash shim → `uv run --project tools qwork` |
| `tools/pyproject.toml` | Package metadata, script entry, pytest config |
| `tools/prompts/implement.md` | Prompt template for `start` |
| `tools/src/qwork/errors.py` | `QworkError` — user-facing failure |
| `tools/src/qwork/runner.py` | `run()` subprocess wrapper, `CommandError`, `Runner` protocol |
| `tools/src/qwork/board.py` | `Task`, status constants, board reads/writes, agent transition rules |
| `tools/src/qwork/repo.py` | Task file discovery, worktree path, `Git` operations |
| `tools/src/qwork/template.py` | Prompt rendering with placeholder checks |
| `tools/src/qwork/agents.py` | Agent table, effort validation, launch command construction |
| `tools/src/qwork/context.py` | `Context` (workspace, board, runner, streams, exec) |
| `tools/src/qwork/commands.py` | `board show` / `board set` |
| `tools/src/qwork/start.py` | `start` command |
| `tools/src/qwork/finish.py` | `finish` command |
| `tools/src/qwork/cli.py` | argparse parser, dispatch, error reporting |
| `tools/tests/helpers.py` | `item()`, `FakeRunner`, `RecordingExec`, `git()`, `write()` |
| `tools/tests/conftest.py` | Isolated git config, temporary workspace, `make_ctx` |

---

### Task 1: Workspace foundation

**Files:**
- Modify: `.gitignore`
- Create: `AGENTS.md`, `CLAUDE.md`
- Modify: `q-workspace/` symlinks
- Modify: `README.md` (Board Status Workflow table)
- Modify: `docs/development/specs/workspace-agent-launcher-spec.md` §1.1

**Interfaces:**
- Consumes: nothing.
- Produces: tracked meta-repo; `AGENTS.md` references `./work board show|set` (implemented in Task 6).

- [ ] **Step 1: Confirm the `.gitignore` and `.ignore` contents**

`.gitignore` must be exactly:

```gitignore
/q_backend/
/q_contracts/
/q_core/
/q_frontend/
/q_terminal/
/.worktrees/
/q-workspace/.serena/cache/
/q-workspace/.serena/logs/
tools/.venv/
__pycache__/
.pytest_cache/
/.agents/
/.codex/
```

`.ignore` (already committed) must be:

```
# q/.gitignore hides the sibling repos from git. Search tools built on ripgrep
# (Claude Code, Codex) also honour .gitignore, so re-include the repos here.
# Each repo's own .gitignore still applies inside it.
!/q_backend/
!/q_contracts/
!/q_core/
!/q_frontend/
!/q_terminal/
```

- [ ] **Step 2: Fix the Serena symlinks**

```bash
cd q-workspace
rm backend desktop frontend shared worker
for r in q_backend q_contracts q_core q_frontend q_terminal; do ln -s "../$r" "$r"; done
ls -l
```

Expected: five links, each resolving (`ls q_core/` lists files). Then check `.serena/project.yml` has no references to the old names:

```bash
grep -nE '\b(backend|desktop|frontend|shared|worker)/' .serena/project.yml || echo "no old paths"
```

Expected: `no old paths`.

- [ ] **Step 3: Write `CLAUDE.md`**

```markdown
@AGENTS.md
```

- [ ] **Step 4: Write `AGENTS.md`**

````markdown
# Q workspace — agent instructions

You are in `q/`, the workspace root of the Q quantitative trading platform. `q/` is a
small meta-repo; the product code lives in independent git repositories inside it.

## Repositories

| Path | Role |
|---|---|
| `q_contracts/` | Source of truth for versioned schemas and wire contracts (control API, stream envelope, Wine edge, lake manifests) and their code generators |
| `q_backend/` | FastAPI control API, Dramatiq workers, PostgreSQL ledger/outbox, Redis Streams (Python) |
| `q_core/` | Rust workspace of shared deterministic primitives, bound to Python (PyO3) and Qt (cxx-qt) |
| `q_frontend/` | Tauri 2 + React 19 research desktop UI |
| `q_terminal/` | Qt 6 / QML live trading and operations terminal |

- Each repository has its own history, CI, `Makefile` and branches (`development`, `main`,
  sometimes `staging`). Run git commands inside the repository you are changing.
- Contracts flow one way: `q_contracts` → consumers pin a commit in `CONTRACTS_REV` and vendor
  generated code. Never hand-edit vendored contract code; verify with `make contracts-check`
  in the consumer.
- Before working in a repository, read its `AGENTS.md` (if present) and `README.md`. They
  contain repo-specific commands and caveats (for example, `q_frontend` tests need
  `TZ=America/Sao_Paulo`).
- `q-workspace/` is a symlink view for the Serena code-navigation server. Never edit files
  through it; use the real repository paths.
- `.worktrees/` holds task worktrees created by `./work start --worktree`.
- The `q/` meta-repo itself tracks only workspace files (`AGENTS.md`, `README.md`, `docs/`,
  `tools/`, `work`, `q-workspace/`).

## Project board

Delivery is tracked on the GitHub Project <https://github.com/users/GuilhermeFortuna/projects/2>.
Each task is an issue titled `Q-NNN — <title>` in the repository that owns it. Its spec and
plan live in that repository at `docs/development/specs/Q-NNN-*-spec.md` and
`docs/development/plans/Q-NNN-*-plan.md`.

| Status | Meaning | Set by |
|---|---|---|
| `Blocked` | Prerequisites incomplete or plan not yet approved | human, or agent when stuck |
| `Todo` | Plan approved, ready to build | human only |
| `In Progress` | An agent session is working on it | `./work start` |
| `In Review` | Work committed on a local task branch, checks run, awaiting human review | agent |
| `Done` | Merged into `development` | `./work finish` (human) |

### Rules for agents

- Work only on the task you were launched for. If asked to implement a board task that is not
  already `In Progress`, ask the human to launch it with `./work start <ID> --agent <agent>`.
- Inspect a task with `./work board show <ID>`.
- When the work is complete and checks pass:
  `./work board set <ID> in-review -m "<what was done; checks run and results; open follow-ups>"`
- When you cannot continue:
  `./work board set <ID> blocked -m "<what blocks you and what is needed>"`, then stop.
- Never push, merge, check out `development`/`main`/`staging`, close issues, or change board
  statuses any other way (no `gh project item-edit`, no web UI).
- Commit on the task branch with focused commits that follow the repository's conventions.
- Use the `gh` CLI for GitHub operations.
````

- [ ] **Step 5: Add `In Review` to the README status table**

In `README.md`, replace the Board Status Workflow table with:

```markdown
| Status | Definition |
| :--- | :--- |
| **`Blocked`** | Prerequisites incomplete, or technical specification/plan pending review. |
| **`Todo`** | Prerequisite satisfied, implementation plan approved, ready to build. |
| **`In Progress`** | Actively under active development. |
| **`In Review`** | Implementation committed on a local task branch, checks run, awaiting human review and merge. |
| **`Done`** | Automated tests passing, cross-repo verification clean, acceptance documented. |
```

- [ ] **Step 6: Record `.ignore` in the spec**

In the spec §1.1, after the gitignore block, add:

```markdown
Because ripgrep-based agent search tools honour `.gitignore`, a `q/.ignore` file re-includes
the five repositories (`!/q_backend/` …); each repository's own `.gitignore` still applies.
```

- [ ] **Step 7: Verify**

```bash
git status --short
rg -l 'Q-010' | head -3
ls q-workspace/q_contracts/ | head -3
```

Expected: `git status` lists `.gitignore`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/…spec.md`, `q-workspace/`, `q_workspace.code-workspace` and nothing under `q_*`; `rg` finds files inside the sibling repos; the `q_contracts` link resolves.

- [ ] **Step 8: Commit**

```bash
git add .gitignore AGENTS.md CLAUDE.md README.md q_workspace.code-workspace q-workspace docs
git commit -m "Add workspace agent instructions, Serena links and In Review status

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git ls-files q-workspace
```

Expected `git ls-files`: the five symlinks, `q-workspace/.serena/.gitignore`, `q-workspace/.serena/project.yml` (and `memories/` files if any) — no `cache/` or `logs/`.

- [ ] **Step 9: Ask the human to add the board option**

Tell the human: "Add an `In Review` option to the project's Status field (Project → Settings → Status), placed between `In Progress` and `Done`." Do not do this through the API.

---

### Task 2: Package scaffold, runner and board reads

**Files:**
- Create: `work`, `tools/pyproject.toml`, `tools/src/qwork/__init__.py`, `tools/src/qwork/errors.py`, `tools/src/qwork/runner.py`, `tools/src/qwork/board.py`
- Test: `tools/tests/helpers.py`, `tools/tests/test_runner.py`, `tools/tests/test_board_read.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `qwork.errors.QworkError(Exception)`
  - `qwork.runner.run(args: Sequence[str], cwd: Path | None = None) -> str`; `CommandError(QworkError)` with `.command: list[str]`, `.returncode: int`, `.stderr: str`; `Runner` protocol with the same call signature as `run`.
  - `qwork.board`: constants `OWNER`, `PROJECT_NUMBER`, `BLOCKED`, `TODO`, `IN_PROGRESS`, `IN_REVIEW`, `DONE`; `slugify(text: str) -> str`; `validate_task_id(task_id: str) -> str`; frozen dataclass `Task(id, title, status, repo_full, issue_number, issue_url, depends_on: tuple[str, ...], item_id)` with properties `repo -> str` and `branch -> str`; `parse_task(item: dict) -> Task`; `class Board(runner: Runner = run)` with `task(task_id: str) -> Task`.
  - `tests/helpers.py`: `STATUS_OPTIONS`, `item(...)`, `FakeRunner(items, status_options=STATUS_OPTIONS)` with `.calls`, `.gh(*prefix)`, `.status_edits()`.

- [ ] **Step 1: Create the package files**

`tools/pyproject.toml`:

```toml
[project]
name = "qwork"
version = "0.1.0"
description = "Launch AI coding agents on Q project board tasks"
requires-python = ">=3.12"
dependencies = []

[project.scripts]
qwork = "qwork.cli:entry"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/qwork"]

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["tests"]
```

`tools/src/qwork/__init__.py`:

```python
"""Launch AI coding agents on Q project board tasks."""
```

`tools/src/qwork/errors.py`:

```python
"""User-facing errors: printed as one line, exit code 1."""


class QworkError(Exception):
    """A failure the user can act on."""
```

`work` (then `chmod +x work`):

```bash
#!/usr/bin/env bash
# Q workspace task launcher. See AGENTS.md and tools/.
set -euo pipefail
root="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
export QWORK_WORKSPACE="$root"
exec uv run --quiet --project "$root/tools" qwork "$@"
```

- [ ] **Step 2: Write the failing runner tests**

`tools/tests/test_runner.py`:

```python
import sys

import pytest

from qwork.errors import QworkError
from qwork.runner import CommandError, run


def test_run_returns_stdout():
    assert run([sys.executable, "-c", "print('hi')"]) == "hi\n"


def test_run_raises_command_error_with_stderr():
    with pytest.raises(CommandError) as info:
        run([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"])
    assert info.value.returncode == 3
    assert info.value.stderr == "boom"
    assert "boom" in str(info.value)


def test_run_missing_executable_is_a_user_error():
    with pytest.raises(QworkError, match="not on PATH"):
        run(["definitely-not-a-real-command-xyz"])
```

- [ ] **Step 3: Write the test helpers and failing board read tests**

`tools/tests/helpers.py`:

```python
"""Shared test helpers: canned board items and a fake gh runner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from qwork.runner import run

STATUS_OPTIONS = ("Blocked", "Todo", "In Progress", "In Review", "Done")


def item(task_id, title, status, *, repo="q_backend", number=1, depends=None) -> dict:
    full = f"GuilhermeFortuna/{repo}"
    data = {
        "id": f"PVTI_{task_id}",
        "title": f"{task_id} — {title}",
        "status": status,
        "repository": f"https://github.com/{full}",
        "content": {
            "type": "Issue",
            "number": number,
            "repository": full,
            "title": f"{task_id} — {title}",
            "url": f"https://github.com/{full}/issues/{number}",
        },
    }
    if depends is not None:
        data["depends on"] = depends
    return data


class FakeRunner:
    """Answers gh commands from canned board data and runs git for real."""

    def __init__(self, items, status_options=STATUS_OPTIONS):
        self.items = list(items)
        self.status_options = status_options
        self.calls: list[list[str]] = []

    def __call__(self, args, cwd=None):
        args = [str(a) for a in args]
        if args[0] == "git":
            return run(args, cwd)
        self.calls.append(args)
        head = args[:3]
        if head == ["gh", "project", "item-list"]:
            return json.dumps({"items": self.items, "totalCount": len(self.items)})
        if head == ["gh", "project", "view"]:
            return json.dumps({"id": "PVT_test", "number": 2})
        if head == ["gh", "project", "field-list"]:
            options = [{"id": f"opt-{name}", "name": name} for name in self.status_options]
            return json.dumps(
                {
                    "fields": [
                        {"id": "F_title", "name": "Title", "type": "ProjectV2Field"},
                        {
                            "id": "F_status",
                            "name": "Status",
                            "type": "ProjectV2SingleSelectField",
                            "options": options,
                        },
                    ]
                }
            )
        if head in (["gh", "project", "item-edit"], ["gh", "issue", "comment"], ["gh", "issue", "close"]):
            return ""
        raise AssertionError(f"unexpected command: {args}")

    def gh(self, *prefix: str) -> list[list[str]]:
        return [c for c in self.calls if c[: len(prefix)] == list(prefix)]

    def status_edits(self) -> list[tuple[str, str]]:
        return [
            (c[c.index("--id") + 1], c[c.index("--single-select-option-id") + 1].removeprefix("opt-"))
            for c in self.gh("gh", "project", "item-edit")
        ]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
```

`tools/tests/test_board_read.py`:

```python
import pytest

from helpers import FakeRunner, item
from qwork.board import Board, slugify
from qwork.errors import QworkError


def test_task_is_parsed_from_board_item():
    board = Board(FakeRunner([item("Q-011", "Redis Streams relay and ephemeral publisher", "Todo", number=2, depends="Q-010")]))
    task = board.task("Q-011")
    assert task.id == "Q-011"
    assert task.status == "Todo"
    assert task.repo_full == "GuilhermeFortuna/q_backend"
    assert task.repo == "q_backend"
    assert task.issue_number == 2
    assert task.issue_url == "https://github.com/GuilhermeFortuna/q_backend/issues/2"
    assert task.depends_on == ("Q-010",)
    assert task.item_id == "PVTI_Q-011"
    assert task.branch == "Q-011-redis-streams-relay-and-ephemeral-publisher"


def test_depends_on_accepts_several_ids_and_blank():
    board = Board(FakeRunner([item("Q-012", "A", "Todo", depends="Q-009, Q-010 Q-011"), item("Q-013", "B", "Todo")]))
    assert board.task("Q-012").depends_on == ("Q-009", "Q-010", "Q-011")
    assert board.task("Q-013").depends_on == ()


@pytest.mark.parametrize(
    ("text", "slug"),
    [
        ("Transactional outbox", "transactional-outbox"),
        ("Job events (on) the stream!", "job-events-on-the-stream"),
        ("  Tauri shell stops owning backend processes ", "tauri-shell-stops-owning-backend-processes"),
    ],
)
def test_slugify(text, slug):
    assert slugify(text) == slug


def test_unknown_task_is_an_error():
    with pytest.raises(QworkError, match="Q-099 is not on the board"):
        Board(FakeRunner([item("Q-010", "A", "Todo")])).task("Q-099")


def test_duplicate_task_is_an_error():
    with pytest.raises(QworkError, match="matches 2 board items"):
        Board(FakeRunner([item("Q-010", "A", "Todo"), item("Q-010", "B", "Todo")])).task("Q-010")


def test_invalid_task_id_is_an_error():
    with pytest.raises(QworkError, match="invalid task ID"):
        Board(FakeRunner([])).task("Q-10")


def test_prefix_must_be_the_whole_id():
    with pytest.raises(QworkError, match="Q-001 is not on the board"):
        Board(FakeRunner([item("Q-0011", "A", "Todo")])).task("Q-001")


def test_draft_items_are_rejected():
    draft = item("Q-010", "A", "Todo")
    draft["content"] = {"type": "DraftIssue", "title": draft["title"]}
    with pytest.raises(QworkError, match="is not an issue"):
        Board(FakeRunner([draft])).task("Q-010")


def test_board_items_are_listed_once():
    fake = FakeRunner([item("Q-010", "A", "Todo"), item("Q-011", "B", "Todo")])
    board = Board(fake)
    board.task("Q-010")
    board.task("Q-011")
    assert len(fake.gh("gh", "project", "item-list")) == 1
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run --project tools pytest tools/tests -q`
Expected: collection errors — `ModuleNotFoundError: No module named 'qwork.runner'` / `'qwork.board'`.

- [ ] **Step 5: Implement `runner.py`**

```python
"""The single place qwork runs external commands (gh, git)."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from qwork.errors import QworkError


class CommandError(QworkError):
    def __init__(self, command: Sequence[str], returncode: int, stderr: str) -> None:
        self.command = list(command)
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"`{' '.join(self.command)}` failed ({returncode}): {stderr.strip()}")


class Runner(Protocol):
    def __call__(self, args: Sequence[str], cwd: Path | None = None) -> str: ...


def run(args: Sequence[str], cwd: Path | None = None) -> str:
    try:
        proc = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise QworkError(f"'{args[0]}' is not installed or not on PATH") from None
    if proc.returncode != 0:
        raise CommandError(args, proc.returncode, proc.stderr)
    return proc.stdout
```

- [ ] **Step 6: Implement `board.py` (reads)**

```python
"""Read and update tasks on the Q GitHub Project board through the gh CLI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cached_property

from qwork.errors import QworkError
from qwork.runner import Runner, run

OWNER = "GuilhermeFortuna"
PROJECT_NUMBER = 2

BLOCKED = "Blocked"
TODO = "Todo"
IN_PROGRESS = "In Progress"
IN_REVIEW = "In Review"
DONE = "Done"

TASK_ID_RE = re.compile(r"^Q-\d{3}$")
TASK_ID_IN_TEXT_RE = re.compile(r"Q-\d{3}")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def validate_task_id(task_id: str) -> str:
    if not TASK_ID_RE.match(task_id):
        raise QworkError(f"invalid task ID '{task_id}' (expected Q-NNN)")
    return task_id


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    status: str
    repo_full: str
    issue_number: int
    issue_url: str
    depends_on: tuple[str, ...]
    item_id: str

    @property
    def repo(self) -> str:
        return self.repo_full.split("/", 1)[1]

    @property
    def branch(self) -> str:
        name = re.sub(rf"^{re.escape(self.id)}\s*[—–-]?\s*", "", self.title)
        return f"{self.id}-{slugify(name)}"


def parse_task(item: dict) -> Task:
    content = item.get("content") or {}
    title = item.get("title", "")
    if content.get("type") != "Issue":
        raise QworkError(f"board item '{title}' is not an issue")
    return Task(
        id=title.split()[0],
        title=title,
        status=item.get("status") or "",
        repo_full=content["repository"],
        issue_number=int(content["number"]),
        issue_url=content["url"],
        depends_on=tuple(TASK_ID_IN_TEXT_RE.findall(item.get("depends on") or "")),
        item_id=item["id"],
    )


class Board:
    def __init__(self, runner: Runner = run) -> None:
        self._run = runner

    def _project_json(self, *args: str) -> dict:
        return json.loads(self._run(["gh", "project", *args, "--owner", OWNER, "--format", "json"]))

    @cached_property
    def _items(self) -> list[dict]:
        return self._project_json("item-list", str(PROJECT_NUMBER), "--limit", "500")["items"]

    def task(self, task_id: str) -> Task:
        validate_task_id(task_id)
        matches = [i for i in self._items if i.get("title", "").startswith(f"{task_id} ")]
        if not matches:
            raise QworkError(f"{task_id} is not on the board")
        if len(matches) > 1:
            raise QworkError(f"{task_id} matches {len(matches)} board items")
        return parse_task(matches[0])
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run --project tools pytest tools/tests -q`
Expected: all tests in `test_runner.py` and `test_board_read.py` pass.

- [ ] **Step 8: Commit**

```bash
git add work tools/pyproject.toml tools/uv.lock tools/src tools/tests
git commit -m "Add qwork package with runner and board reads

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Board writes and agent transition rules

**Files:**
- Modify: `tools/src/qwork/board.py`
- Test: `tools/tests/test_board_write.py`

**Interfaces:**
- Consumes: `Board`, `Task`, status constants, `QworkError` (Task 2); `FakeRunner`, `item` (Task 2 helpers).
- Produces:
  - `AGENT_TARGETS: dict[str, str] = {"in-review": IN_REVIEW, "blocked": BLOCKED}`
  - `check_agent_transition(task: Task, target: str, message: str | None) -> str` — returns the board status name.
  - `Board.set_status(task: Task, status: str) -> None`
  - `Board.comment(task: Task, body: str) -> None`
  - `Board.close(task: Task, comment: str) -> None`

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_board_write.py`:

```python
import pytest

from helpers import FakeRunner, item
from qwork.board import Board, check_agent_transition
from qwork.errors import QworkError


def make(status="In Progress", **kwargs):
    fake = FakeRunner([item("Q-010", "Transactional outbox", status)], **kwargs)
    board = Board(fake)
    return fake, board, board.task("Q-010")


def test_set_status_edits_the_item_with_resolved_ids():
    fake, board, task = make()
    board.set_status(task, "In Review")
    [edit] = fake.gh("gh", "project", "item-edit")
    assert edit[edit.index("--project-id") + 1] == "PVT_test"
    assert edit[edit.index("--field-id") + 1] == "F_status"
    assert fake.status_edits() == [("PVTI_Q-010", "In Review")]


def test_set_status_without_board_option_is_an_error():
    fake, board, task = make(status_options=("Blocked", "Todo", "In Progress", "Done"))
    with pytest.raises(QworkError, match="no 'In Review' option"):
        board.set_status(task, "In Review")
    assert fake.gh("gh", "project", "item-edit") == []


def test_field_ids_are_resolved_once():
    fake, board, task = make()
    board.set_status(task, "In Review")
    board.set_status(task, "Done")
    assert len(fake.gh("gh", "project", "view")) == 1
    assert len(fake.gh("gh", "project", "field-list")) == 1


def test_comment_and_close_target_the_issue():
    fake, board, task = make()
    board.comment(task, "hello")
    board.close(task, "merged")
    assert fake.gh("gh", "issue", "comment") == [
        ["gh", "issue", "comment", "1", "--repo", "GuilhermeFortuna/q_backend", "--body", "hello"]
    ]
    assert fake.gh("gh", "issue", "close") == [
        ["gh", "issue", "close", "1", "--repo", "GuilhermeFortuna/q_backend", "--comment", "merged"]
    ]


def test_agent_can_move_in_progress_to_in_review():
    _, _, task = make()
    assert check_agent_transition(task, "in-review", None) == "In Review"


def test_agent_can_block_with_a_reason():
    _, _, task = make()
    assert check_agent_transition(task, "blocked", "needs Q-009 schema") == "Blocked"


def test_blocked_requires_a_reason():
    _, _, task = make()
    with pytest.raises(QworkError, match="requires -m"):
        check_agent_transition(task, "blocked", None)


@pytest.mark.parametrize("status", ["Todo", "Blocked", "In Review", "Done"])
def test_agent_transitions_only_from_in_progress(status):
    _, _, task = make(status=status)
    with pytest.raises(QworkError, match="only from 'In Progress'"):
        check_agent_transition(task, "in-review", "x")


@pytest.mark.parametrize("target", ["done", "todo", "in-progress"])
def test_agent_cannot_choose_other_targets(target):
    _, _, task = make()
    with pytest.raises(QworkError, match="agents may only set"):
        check_agent_transition(task, target, "x")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project tools pytest tools/tests/test_board_write.py -q`
Expected: `ImportError: cannot import name 'check_agent_transition'`.

- [ ] **Step 3: Implement**

Add to `board.py` after the status constants:

```python
AGENT_TARGETS = {"in-review": IN_REVIEW, "blocked": BLOCKED}
```

Add after `parse_task`:

```python
def check_agent_transition(task: Task, target: str, message: str | None) -> str:
    if target not in AGENT_TARGETS:
        raise QworkError(f"agents may only set: {', '.join(AGENT_TARGETS)}")
    if task.status != IN_PROGRESS:
        raise QworkError(f"{task.id} is '{task.status}'; agents can change status only from '{IN_PROGRESS}'")
    if target == "blocked" and not message:
        raise QworkError("blocked requires -m with the reason")
    return AGENT_TARGETS[target]
```

Add to `class Board`:

```python
    @cached_property
    def _status_field(self) -> tuple[str, str, dict[str, str]]:
        project_id = self._project_json("view", str(PROJECT_NUMBER))["id"]
        fields = self._project_json("field-list", str(PROJECT_NUMBER))["fields"]
        status = next((f for f in fields if f["name"] == "Status"), None)
        if status is None:
            raise QworkError("board has no Status field")
        return project_id, status["id"], {o["name"]: o["id"] for o in status["options"]}

    def set_status(self, task: Task, status: str) -> None:
        project_id, field_id, options = self._status_field
        if status not in options:
            raise QworkError(f"board Status has no '{status}' option; add it in the GitHub project settings")
        self._run(
            [
                "gh", "project", "item-edit",
                "--id", task.item_id,
                "--project-id", project_id,
                "--field-id", field_id,
                "--single-select-option-id", options[status],
            ]
        )

    def comment(self, task: Task, body: str) -> None:
        self._run(["gh", "issue", "comment", str(task.issue_number), "--repo", task.repo_full, "--body", body])

    def close(self, task: Task, comment: str) -> None:
        self._run(["gh", "issue", "close", str(task.issue_number), "--repo", task.repo_full, "--comment", comment])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project tools pytest tools/tests -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tools/src/qwork/board.py tools/tests/test_board_write.py
git commit -m "Add board status updates, issue comments and agent transition rules

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Task files and git operations

**Files:**
- Create: `tools/src/qwork/repo.py`, `tools/tests/conftest.py`
- Test: `tools/tests/test_repo.py`

**Interfaces:**
- Consumes: `Task`, `Board` (Task 2); `run`, `Runner`, `CommandError` (Task 2); helpers `git`, `write`, `item`, `FakeRunner`.
- Produces:
  - `INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md", "README.md")`
  - frozen dataclass `TaskFiles(repo: Path, spec: Path, plan: Path, instructions: tuple[Path, ...])`
  - `task_files(workspace: Path, task: Task) -> TaskFiles`
  - `worktree_path(workspace: Path, task: Task) -> Path`
  - `class Git(path: Path, runner: Runner = run)` with: `branch_exists(name) -> bool`, `current_branch() -> str`, `is_dirty(include_untracked: bool = False) -> bool`, `fetch(remote, branch) -> None`, `commits_behind(local, upstream) -> int`, `create_branch(name, start) -> None`, `checkout(name) -> None`, `add_worktree(path: Path, branch) -> None`, `remove_worktree(path: Path) -> None`, `merge_no_ff(branch, message) -> str` (returns merge commit SHA; on failure aborts and raises `QworkError`), `push(remote, branch) -> None`.
  - conftest fixtures: autouse `isolated_git`; `workspace` → `Path` of a temp `q/` containing `q_backend` (on `development`, pushed to a bare `origin` with `main` and `development`; contains `README.md`, the Q-010 spec and plan).

- [ ] **Step 1: Write the conftest**

`tools/tests/conftest.py`:

```python
import pytest

from helpers import git, write


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
```

- [ ] **Step 2: Write the failing tests**

`tools/tests/test_repo.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run --project tools pytest tools/tests/test_repo.py -q`
Expected: `ModuleNotFoundError: No module named 'qwork.repo'`.

- [ ] **Step 4: Implement `repo.py`**

```python
"""Local repository layout and git operations for a task."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qwork.board import Task
from qwork.errors import QworkError
from qwork.runner import CommandError, Runner, run

INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md", "README.md")


@dataclass(frozen=True)
class TaskFiles:
    repo: Path
    spec: Path
    plan: Path
    instructions: tuple[Path, ...]


def _single(directory: Path, pattern: str, kind: str, task_id: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if not matches:
        raise QworkError(f"{task_id}: no {kind} matching {directory / pattern}")
    if len(matches) > 1:
        raise QworkError(f"{task_id}: {len(matches)} {kind} files match {directory / pattern}")
    return matches[0]


def task_files(workspace: Path, task: Task) -> TaskFiles:
    repo = workspace / task.repo
    if not repo.is_dir():
        raise QworkError(f"{task.id}: repository {task.repo} is not cloned at {repo}")
    docs = repo / "docs" / "development"
    return TaskFiles(
        repo=repo,
        spec=_single(docs / "specs", f"{task.id}-*-spec.md", "spec", task.id),
        plan=_single(docs / "plans", f"{task.id}-*-plan.md", "plan", task.id),
        instructions=tuple(repo / name for name in INSTRUCTION_FILES if (repo / name).is_file()),
    )


def worktree_path(workspace: Path, task: Task) -> Path:
    return workspace / ".worktrees" / task.repo / task.branch


class Git:
    def __init__(self, path: Path, runner: Runner = run) -> None:
        self.path = path
        self._run = runner

    def _git(self, *args: str) -> str:
        return self._run(["git", *args], cwd=self.path)

    def branch_exists(self, name: str) -> bool:
        try:
            self._git("rev-parse", "--verify", "--quiet", f"refs/heads/{name}")
        except CommandError:
            return False
        return True

    def current_branch(self) -> str:
        return self._git("branch", "--show-current").strip()

    def is_dirty(self, include_untracked: bool = False) -> bool:
        mode = "normal" if include_untracked else "no"
        return bool(self._git("status", "--porcelain", f"--untracked-files={mode}").strip())

    def fetch(self, remote: str, branch: str) -> None:
        self._git("fetch", "--quiet", remote, branch)

    def commits_behind(self, local: str, upstream: str) -> int:
        return int(self._git("rev-list", "--count", f"{local}..{upstream}").strip())

    def create_branch(self, name: str, start: str) -> None:
        self._git("branch", name, start)

    def checkout(self, name: str) -> None:
        self._git("checkout", "--quiet", name)

    def add_worktree(self, path: Path, branch: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._git("worktree", "add", "--quiet", str(path), branch)

    def remove_worktree(self, path: Path) -> None:
        self._git("worktree", "remove", str(path))

    def merge_no_ff(self, branch: str, message: str) -> str:
        try:
            self._git("merge", "--no-ff", "-m", message, branch)
        except CommandError as exc:
            try:
                self._git("merge", "--abort")
            except CommandError:
                pass
            raise QworkError(f"merging {branch} failed and was aborted: {exc.stderr.strip()}") from None
        return self._git("rev-parse", "HEAD").strip()

    def push(self, remote: str, branch: str) -> None:
        self._git("push", "--quiet", remote, branch)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --project tools pytest tools/tests -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add tools/src/qwork/repo.py tools/tests/conftest.py tools/tests/test_repo.py
git commit -m "Add task file discovery and git operations

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Prompt template and agent commands

**Files:**
- Create: `tools/src/qwork/template.py`, `tools/src/qwork/agents.py`, `tools/prompts/implement.md`
- Test: `tools/tests/test_template.py`, `tools/tests/test_agents.py`

**Interfaces:**
- Consumes: `QworkError` (Task 2).
- Produces:
  - `template.PROMPTS_DIR: Path`; `template.render(name: str, values: dict[str, str], prompts_dir: Path = PROMPTS_DIR) -> str` — errors on unknown placeholders and on values the template does not use.
  - `implement.md` placeholders, exactly: `id title repo issue_url spec plan workdir branch resume repo_agents`.
  - `agents.DEFAULT_EFFORT = "medium"`; frozen dataclass `AgentSpec(name, executable, efforts: tuple[str, ...])`; `AGENTS: dict[str, AgentSpec]` with keys `claude codex cursor antigravity`; frozen dataclass `Launch(argv: list[str], notice: str | None)`; `build_command(agent: str, prompt: str, effort: str | None, model: str | None) -> Launch` (prompt is always the last argv element).

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_template.py`:

```python
import pytest

from qwork.errors import QworkError
from qwork.template import render

VALUES = {
    "id": "Q-010",
    "title": "Q-010 — Transactional outbox",
    "repo": "q_backend",
    "issue_url": "https://github.com/GuilhermeFortuna/q_backend/issues/1",
    "spec": "q_backend/docs/development/specs/Q-010-transactional-outbox-spec.md",
    "plan": "q_backend/docs/development/plans/Q-010-transactional-outbox-plan.md",
    "workdir": "q_backend",
    "branch": "Q-010-transactional-outbox",
    "resume": "",
    "repo_agents": "`q_backend/README.md`",
}


def test_implement_template_renders(tmp_path):
    text = render("implement", VALUES)
    assert "Q-010 — Transactional outbox" in text
    assert "q_backend/docs/development/plans/Q-010-transactional-outbox-plan.md" in text
    assert "./work board set Q-010 in-review" in text
    assert "./work board set Q-010 blocked" in text
    assert "$" not in text.replace("$ ", "")


def test_unknown_placeholder_is_an_error(tmp_path):
    (tmp_path / "t.md").write_text("Hello $who")
    with pytest.raises(QworkError, match=r"unknown placeholder \$who"):
        render("t", {}, prompts_dir=tmp_path)


def test_unused_value_is_an_error(tmp_path):
    (tmp_path / "t.md").write_text("Hello $who")
    with pytest.raises(QworkError, match="does not use: extra"):
        render("t", {"who": "x", "extra": "y"}, prompts_dir=tmp_path)


def test_missing_template_is_an_error(tmp_path):
    with pytest.raises(QworkError, match="not found"):
        render("nope", {}, prompts_dir=tmp_path)
```

`tools/tests/test_agents.py`:

```python
import pytest

from qwork.agents import AGENTS, build_command
from qwork.errors import QworkError


def test_claude_default_effort():
    launch = build_command("claude", "PROMPT", None, None)
    assert launch.argv == ["claude", "--effort", "medium", "PROMPT"]
    assert launch.notice is None


def test_claude_with_model_and_max_effort():
    assert build_command("claude", "P", "max", "opus").argv == ["claude", "--model", "opus", "--effort", "max", "P"]


def test_codex_effort_through_config():
    assert build_command("codex", "P", "high", "gpt-5").argv == ["codex", "-m", "gpt-5", "-c", "model_reasoning_effort=high", "P"]


def test_cursor_effort_is_a_model_parameter():
    assert build_command("cursor", "P", "high", "sonnet-5").argv == ["agent", "--model", "sonnet-5[effort=high]", "P"]


def test_cursor_without_model_skips_default_effort_with_notice():
    launch = build_command("cursor", "P", None, None)
    assert launch.argv == ["agent", "P"]
    assert "effort not applied" in launch.notice


def test_cursor_explicit_effort_without_model_is_an_error():
    with pytest.raises(QworkError, match="pass --model"):
        build_command("cursor", "P", "high", None)


def test_antigravity_interactive_prompt():
    assert build_command("antigravity", "P", None, "gemini-3-pro").argv == [
        "agy", "--model", "gemini-3-pro", "--effort", "medium", "-i", "P"
    ]


@pytest.mark.parametrize(("agent", "effort"), [("antigravity", "xhigh"), ("codex", "max"), ("claude", "minimal")])
def test_unsupported_effort_is_an_error(agent, effort):
    with pytest.raises(QworkError, match=f"{agent} does not support effort '{effort}'"):
        build_command(agent, "P", effort, None)


def test_executables():
    assert {name: spec.executable for name, spec in AGENTS.items()} == {
        "claude": "claude", "codex": "codex", "cursor": "agent", "antigravity": "agy"
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project tools pytest tools/tests/test_template.py tools/tests/test_agents.py -q`
Expected: `ModuleNotFoundError: No module named 'qwork.template'` / `'qwork.agents'`.

- [ ] **Step 3: Implement `template.py`**

```python
"""Render agent prompt templates from tools/prompts."""

from __future__ import annotations

import string
from pathlib import Path

from qwork.errors import QworkError

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def render(name: str, values: dict[str, str], prompts_dir: Path = PROMPTS_DIR) -> str:
    path = prompts_dir / f"{name}.md"
    if not path.is_file():
        raise QworkError(f"prompt template not found: {path}")
    template = string.Template(path.read_text(encoding="utf-8"))
    unused = sorted(set(values) - set(template.get_identifiers()))
    if unused:
        raise QworkError(f"prompt template {path.name} does not use: {', '.join(unused)}")
    try:
        return template.substitute(values)
    except KeyError as exc:
        raise QworkError(f"prompt template {path.name} uses unknown placeholder ${exc.args[0]}") from None
    except ValueError as exc:
        raise QworkError(f"prompt template {path.name} is malformed: {exc}") from None
```

- [ ] **Step 4: Write `tools/prompts/implement.md`**

```markdown
You are implementing board task $title.

## Task

- Issue: $issue_url
- Repository: `$repo`
- Spec: `$spec`
- Plan: `$plan`
- Working directory: `$workdir`
- Branch: `$branch` (already checked out there)
$resume
## Before you start

1. Read `AGENTS.md` in the workspace root.
2. Read the repository instructions: $repo_agents.
3. Read the issue (`gh issue view $issue_url`), then the spec and the plan in full.

## Doing the work

- Work only inside `$workdir`, on `$branch`.
- Follow the plan task by task. Tick plan checkboxes as you complete steps.
- Commit locally with focused commits that follow the repository's conventions.
- Run the repository's documented checks (tests, lint, type checks, `make contracts-check`
  where relevant) and fix failures caused by your change.
- Never push, merge, check out `development`, `main` or `staging`, or close the issue.
- Change the board status only with the commands below.

## Finishing

When the work is complete and the checks pass, run:

    ./work board set $id in-review -m "<what was done; checks run and their results; open follow-ups>"

If you cannot continue, run the following and stop:

    ./work board set $id blocked -m "<what blocks you and what is needed>"
```

- [ ] **Step 5: Implement `agents.py`**

```python
"""Supported agent CLIs and how to launch them."""

from __future__ import annotations

from dataclasses import dataclass

from qwork.errors import QworkError

DEFAULT_EFFORT = "medium"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    executable: str
    efforts: tuple[str, ...]


AGENTS = {
    "claude": AgentSpec("claude", "claude", ("low", "medium", "high", "xhigh", "max")),
    "codex": AgentSpec("codex", "codex", ("minimal", "low", "medium", "high", "xhigh")),
    "cursor": AgentSpec("cursor", "agent", ("low", "medium", "high", "xhigh", "max")),
    "antigravity": AgentSpec("antigravity", "agy", ("low", "medium", "high")),
}


@dataclass(frozen=True)
class Launch:
    argv: list[str]
    notice: str | None = None


def build_command(agent: str, prompt: str, effort: str | None, model: str | None) -> Launch:
    spec = AGENTS[agent]
    explicit = effort is not None
    effort = effort or DEFAULT_EFFORT
    if effort not in spec.efforts:
        raise QworkError(f"{agent} does not support effort '{effort}' (allowed: {', '.join(spec.efforts)})")

    if agent == "claude":
        model_args = ["--model", model] if model else []
        return Launch(["claude", *model_args, "--effort", effort, prompt])
    if agent == "codex":
        model_args = ["-m", model] if model else []
        return Launch(["codex", *model_args, "-c", f"model_reasoning_effort={effort}", prompt])
    if agent == "cursor":
        if model:
            return Launch(["agent", "--model", f"{model}[effort={effort}]", prompt])
        if explicit:
            raise QworkError("cursor applies effort through the model; pass --model with --effort")
        return Launch(["agent", prompt], notice="cursor: default effort not applied (no --model given)")
    model_args = ["--model", model] if model else []
    return Launch(["agy", *model_args, "--effort", effort, "-i", prompt])
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run --project tools pytest tools/tests -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add tools/src/qwork/template.py tools/src/qwork/agents.py tools/prompts tools/tests/test_template.py tools/tests/test_agents.py
git commit -m "Add implement prompt template and agent launch commands

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: CLI, context and `board show` / `board set`

**Files:**
- Create: `tools/src/qwork/context.py`, `tools/src/qwork/commands.py`, `tools/src/qwork/cli.py`
- Modify: `tools/tests/helpers.py` (add `RecordingExec`), `tools/tests/conftest.py` (add `make_ctx`)
- Test: `tools/tests/test_cli_board.py`

**Interfaces:**
- Consumes: `Board`, `AGENT_TARGETS`, `check_agent_transition` (Tasks 2–3); `task_files`, `worktree_path`, `Git` (Task 4); `AGENTS`, `DEFAULT_EFFORT` (Task 5).
- Produces:
  - `context.Context` dataclass: `workspace: Path`, `board: Board`, `run: Runner`, `out: TextIO`, `err: TextIO`, `execvp: Callable[[str, list[str]], object]`, `which: Callable[[str], str | None]`; `Context.default() -> Context`; `default_workspace() -> Path` (env `QWORK_WORKSPACE`, else `tools/`'s parent).
  - `commands.board_show(ctx, task_id: str) -> int`; `commands.board_set(ctx, task_id: str, target: str, message: str | None) -> int`.
  - `cli.build_parser() -> argparse.ArgumentParser`; `cli.main(argv: list[str] | None = None, ctx: Context | None = None) -> int`; `cli.entry() -> None`.
  - `cli.main` dispatches `start` to `qwork.start.start(ctx, task_id, agent, effort, model, worktree, dry_run)` and `finish` to `qwork.finish.finish(ctx, task_id, push)` (created in Tasks 7–8; imported lazily inside `main` so this task runs without them).
  - helpers: `RecordingExec` with `.calls: list[list[str]]`; fixture `make_ctx(items, status_options=STATUS_OPTIONS) -> tuple[Context, FakeRunner]` (also `chdir`s into the workspace, restored after the test).

- [ ] **Step 1: Add the test helpers and fixture**

Append to `tools/tests/helpers.py`:

```python
class RecordingExec:
    """Stands in for os.execvp."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, file: str, argv: list[str]) -> None:
        self.calls.append(list(argv))
```

Append to `tools/tests/conftest.py`:

```python
import io

from helpers import STATUS_OPTIONS, FakeRunner, RecordingExec
from qwork.board import Board
from qwork.context import Context


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
```

(Move the new imports to the top of `conftest.py` alongside the existing ones.)

- [ ] **Step 2: Write the failing tests**

`tools/tests/test_cli_board.py`:

```python
from helpers import item
from qwork.cli import main


def test_board_show_prints_task(make_ctx):
    ctx, _ = make_ctx([
        item("Q-010", "Transactional outbox", "Todo", depends="Q-009"),
        item("Q-009", "Stream payload", "Done", repo="q_contracts"),
    ])
    assert main(["board", "show", "Q-010"], ctx) == 0
    out = ctx.out.getvalue()
    assert "Q-010  Todo" in out
    assert "depends:  Q-009 (Done)" in out
    assert "spec:     q_backend/docs/development/specs/Q-010-transactional-outbox-spec.md" in out
    assert "branch:   Q-010-transactional-outbox (not created)" in out
    assert "worktree: none" in out


def test_board_set_in_review_updates_status_and_comments(make_ctx):
    ctx, fake = make_ctx([item("Q-010", "Transactional outbox", "In Progress")])
    assert main(["board", "set", "Q-010", "in-review", "-m", "done; tests pass"], ctx) == 0
    assert fake.status_edits() == [("PVTI_Q-010", "In Review")]
    assert fake.gh("gh", "issue", "comment")[0][-1] == "done; tests pass"
    assert "Q-010: In Progress -> In Review" in ctx.out.getvalue()


def test_board_set_blocked_without_message_fails(make_ctx):
    ctx, fake = make_ctx([item("Q-010", "Transactional outbox", "In Progress")])
    assert main(["board", "set", "Q-010", "blocked"], ctx) == 1
    assert "work: blocked requires -m" in ctx.err.getvalue()
    assert fake.status_edits() == []


def test_board_set_from_todo_fails_without_changes(make_ctx):
    ctx, fake = make_ctx([item("Q-010", "Transactional outbox", "Todo")])
    assert main(["board", "set", "Q-010", "in-review", "-m", "x"], ctx) == 1
    assert fake.status_edits() == []
    assert fake.gh("gh", "issue", "comment") == []


def test_board_set_missing_in_review_option_fails_before_comment(make_ctx):
    ctx, fake = make_ctx(
        [item("Q-010", "Transactional outbox", "In Progress")],
        status_options=("Blocked", "Todo", "In Progress", "Done"),
    )
    assert main(["board", "set", "Q-010", "in-review", "-m", "x"], ctx) == 1
    assert "no 'In Review' option" in ctx.err.getvalue()
    assert fake.gh("gh", "issue", "comment") == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run --project tools pytest tools/tests/test_cli_board.py -q`
Expected: `ModuleNotFoundError: No module named 'qwork.context'`.

- [ ] **Step 4: Implement `context.py`**

```python
"""Everything a command needs from the outside world, injectable for tests."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from qwork.board import Board
from qwork.runner import Runner, run


def default_workspace() -> Path:
    env = os.environ.get("QWORK_WORKSPACE")
    return Path(env).resolve() if env else Path(__file__).resolve().parents[3]


@dataclass
class Context:
    workspace: Path
    board: Board
    run: Runner
    out: TextIO
    err: TextIO
    execvp: Callable[[str, list[str]], object]
    which: Callable[[str], str | None]

    @classmethod
    def default(cls) -> Context:
        return cls(
            workspace=default_workspace(),
            board=Board(run),
            run=run,
            out=sys.stdout,
            err=sys.stderr,
            execvp=os.execvp,
            which=shutil.which,
        )
```

- [ ] **Step 5: Implement `commands.py`**

```python
"""`work board show` and `work board set`."""

from __future__ import annotations

from qwork.board import check_agent_transition
from qwork.context import Context
from qwork.errors import QworkError
from qwork.repo import Git, task_files, worktree_path


def board_show(ctx: Context, task_id: str) -> int:
    task = ctx.board.task(task_id)
    deps = ", ".join(f"{dep} ({ctx.board.task(dep).status})" for dep in task.depends_on) or "none"
    lines = [
        f"{task.id}  {task.status}",
        task.title,
        f"issue:    {task.issue_url}",
        f"repo:     {task.repo}",
        f"depends:  {deps}",
    ]
    try:
        files = task_files(ctx.workspace, task)
    except QworkError as exc:
        lines += [f"branch:   {task.branch}", f"files:    {exc}"]
    else:
        exists = Git(files.repo, ctx.run).branch_exists(task.branch)
        worktree = worktree_path(ctx.workspace, task)
        lines += [
            f"spec:     {files.spec.relative_to(ctx.workspace)}",
            f"plan:     {files.plan.relative_to(ctx.workspace)}",
            f"branch:   {task.branch} ({'exists' if exists else 'not created'})",
            f"worktree: {worktree.relative_to(ctx.workspace) if worktree.exists() else 'none'}",
        ]
    print("\n".join(lines), file=ctx.out)
    return 0


def board_set(ctx: Context, task_id: str, target: str, message: str | None) -> int:
    task = ctx.board.task(task_id)
    status = check_agent_transition(task, target, message)
    ctx.board.set_status(task, status)
    if message:
        ctx.board.comment(task, message)
    print(f"{task.id}: {task.status} -> {status}", file=ctx.out)
    return 0
```

- [ ] **Step 6: Implement `cli.py`**

```python
"""Command-line entry point for ./work."""

from __future__ import annotations

import argparse
import sys

from qwork.agents import AGENTS, DEFAULT_EFFORT
from qwork.board import AGENT_TARGETS
from qwork.context import Context
from qwork.errors import QworkError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="work", description="Launch and finish Q board tasks with AI coding agents.")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="start or resume a task with an agent")
    start.add_argument("task_id", metavar="ID")
    start.add_argument("--agent", required=True, choices=list(AGENTS))
    start.add_argument("--effort", help=f"reasoning effort (default: {DEFAULT_EFFORT})")
    start.add_argument("--model", help="model passed to the agent")
    start.add_argument("--worktree", action="store_true", help="work in q/.worktrees instead of the repo checkout")
    start.add_argument("--dry-run", action="store_true", help="check and print the prompt without changing anything")

    finish = sub.add_parser("finish", help="merge a reviewed task into development and mark it Done")
    finish.add_argument("task_id", metavar="ID")
    finish.add_argument("--push", action="store_true", help="push development to origin after merging")

    board = sub.add_parser("board", help="inspect or update a task on the project board")
    board_sub = board.add_subparsers(dest="board_command", required=True)
    show = board_sub.add_parser("show", help="show a task")
    show.add_argument("task_id", metavar="ID")
    set_ = board_sub.add_parser("set", help="set a task's status (agents)")
    set_.add_argument("task_id", metavar="ID")
    set_.add_argument("target", choices=list(AGENT_TARGETS))
    set_.add_argument("-m", "--message", help="comment posted on the issue")
    return parser


def main(argv: list[str] | None = None, ctx: Context | None = None) -> int:
    args = build_parser().parse_args(argv)
    ctx = ctx or Context.default()
    try:
        if args.command == "start":
            from qwork.start import start

            return start(ctx, args.task_id, args.agent, args.effort, args.model, args.worktree, args.dry_run)
        if args.command == "finish":
            from qwork.finish import finish

            return finish(ctx, args.task_id, args.push)
        from qwork.commands import board_set, board_show

        if args.board_command == "show":
            return board_show(ctx, args.task_id)
        return board_set(ctx, args.task_id, args.target, args.message)
    except QworkError as exc:
        print(f"work: {exc}", file=ctx.err)
        return 1


def entry() -> None:
    sys.exit(main())
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run --project tools pytest tools/tests -q`
Expected: all pass.

- [ ] **Step 8: Smoke-test the shim against the real board (read-only)**

Run: `./work board show Q-016`
Expected: prints `Q-016  Blocked`, the `q_frontend` issue URL, `depends:` with statuses, spec/plan paths under `q_frontend/docs/development/`.

- [ ] **Step 9: Commit**

```bash
git add tools/src/qwork/context.py tools/src/qwork/commands.py tools/src/qwork/cli.py tools/tests
git commit -m "Add work CLI with board show and board set

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: `work start`

**Files:**
- Create: `tools/src/qwork/start.py`
- Test: `tools/tests/test_start.py`

**Interfaces:**
- Consumes: `Context` (Task 6); `Board.task`, `Board.set_status`, `TODO`, `IN_PROGRESS`, `DONE` (Tasks 2–3); `task_files`, `worktree_path`, `Git` (Task 4); `render` (Task 5); `AGENTS`, `build_command` (Task 5); `CommandError` (Task 2).
- Produces: `start(ctx: Context, task_id: str, agent: str, effort: str | None, model: str | None, worktree: bool, dry_run: bool) -> int`.

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_start.py`:

```python
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
    assert "launch: codex -c model_reasoning_effort=high <prompt>" in out
    assert "./work board set Q-010 in-review" in out


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project tools pytest tools/tests/test_start.py -q`
Expected: failures with `ModuleNotFoundError: No module named 'qwork.start'`.

- [ ] **Step 3: Implement `start.py`**

```python
"""`work start`: check a task can start, prepare its branch, launch an agent."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from qwork.agents import AGENTS, build_command
from qwork.board import DONE, IN_PROGRESS, TODO
from qwork.context import Context
from qwork.errors import QworkError
from qwork.repo import Git, task_files, worktree_path
from qwork.runner import CommandError
from qwork.template import render


def _warn_if_behind(ctx: Context, git: Git) -> None:
    try:
        git.fetch("origin", "development")
        behind = git.commits_behind("development", "origin/development")
    except CommandError as exc:
        print(f"work: warning: could not compare development with origin: {exc.stderr.strip()}", file=ctx.err)
        return
    if behind:
        print(f"work: warning: local development is {behind} commit(s) behind origin/development", file=ctx.err)


def start(
    ctx: Context,
    task_id: str,
    agent: str,
    effort: str | None,
    model: str | None,
    worktree: bool,
    dry_run: bool,
) -> int:
    board = ctx.board

    def rel(path: Path) -> str:
        return str(path.relative_to(ctx.workspace))

    task = board.task(task_id)
    if task.status not in (TODO, IN_PROGRESS):
        raise QworkError(f"{task.id} is '{task.status}'; only '{TODO}' or '{IN_PROGRESS}' tasks can be started")
    resuming = task.status == IN_PROGRESS

    unfinished = [dep for dep in (board.task(d) for d in task.depends_on) if dep.status != DONE]
    if unfinished:
        listed = ", ".join(f"{dep.id} ({dep.status})" for dep in unfinished)
        raise QworkError(f"{task.id} depends on unfinished tasks: {listed}")

    files = task_files(ctx.workspace, task)
    executable = AGENTS[agent].executable
    if ctx.which(executable) is None:
        raise QworkError(f"agent '{agent}' needs '{executable}' on PATH")

    git = Git(files.repo, ctx.run)
    branch_exists = git.branch_exists(task.branch)
    if branch_exists and not resuming:
        raise QworkError(
            f"{task.id} is '{TODO}' but branch {task.branch} already exists in {task.repo}; delete or rename it first"
        )

    wt = worktree_path(ctx.workspace, task)
    if worktree:
        workdir = wt
        if wt.exists() and Git(wt, ctx.run).current_branch() != task.branch:
            raise QworkError(f"{rel(wt)} exists but is not on {task.branch}")
    else:
        workdir = files.repo
        if git.is_dirty():
            raise QworkError(f"{task.repo} has uncommitted changes; commit or stash them, or use --worktree")

    _warn_if_behind(ctx, git)

    resume_note = (
        f"\n**Resuming:** `{task.branch}` already has work from an earlier session. Review "
        f"`git log development..{task.branch}` and the plan's checkboxes, then continue.\n"
        if resuming
        else ""
    )
    prompt = render(
        "implement",
        {
            "id": task.id,
            "title": task.title,
            "repo": task.repo,
            "issue_url": task.issue_url,
            "spec": rel(files.spec),
            "plan": rel(files.plan),
            "workdir": rel(workdir),
            "branch": task.branch,
            "resume": resume_note,
            "repo_agents": ", ".join(f"`{rel(p)}`" for p in files.instructions) or "none",
        },
    )
    launch = build_command(agent, prompt, effort, model)
    if launch.notice:
        print(f"work: {launch.notice}", file=ctx.err)

    if dry_run:
        actions = []
        if not branch_exists:
            actions.append(f"create branch {task.branch} from development in {task.repo}")
        if worktree:
            if not wt.exists():
                actions.append(f"add worktree {rel(wt)}")
        else:
            actions.append(f"check out {task.branch} in {task.repo}")
        if not resuming:
            actions.append(f"set {task.id} to '{IN_PROGRESS}'")
        actions.append(f"launch: {shlex.join(launch.argv[:-1])} <prompt>")
        print("Dry run — no changes made. Would:", file=ctx.out)
        for action in actions:
            print(f"  - {action}", file=ctx.out)
        print(f"\n--- prompt ---\n{prompt}", file=ctx.out)
        return 0

    if not branch_exists:
        git.create_branch(task.branch, "development")
    if worktree:
        if not wt.exists():
            git.add_worktree(wt, task.branch)
    else:
        git.checkout(task.branch)
    if not resuming:
        board.set_status(task, IN_PROGRESS)

    print(f"work: {task.id} on {task.branch} in {rel(workdir)}; launching {agent}", file=ctx.err)
    os.chdir(ctx.workspace)
    ctx.execvp(launch.argv[0], launch.argv)
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project tools pytest tools/tests -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tools/src/qwork/start.py tools/tests/test_start.py
git commit -m "Add work start

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: `work finish`

**Files:**
- Create: `tools/src/qwork/finish.py`
- Test: `tools/tests/test_finish.py`

**Interfaces:**
- Consumes: `Context` (Task 6); `Board.task`, `Board.set_status`, `Board.close`, `IN_REVIEW`, `DONE` (Tasks 2–3); `Git`, `worktree_path` (Task 4).
- Produces: `finish(ctx: Context, task_id: str, push: bool) -> int`.

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_finish.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project tools pytest tools/tests/test_finish.py -q`
Expected: failures with `ModuleNotFoundError: No module named 'qwork.finish'`.

- [ ] **Step 3: Implement `finish.py`**

```python
"""`work finish`: merge a reviewed task into development and mark it Done."""

from __future__ import annotations

from qwork.board import DONE, IN_REVIEW
from qwork.context import Context
from qwork.errors import QworkError
from qwork.repo import Git, worktree_path


def finish(ctx: Context, task_id: str, push: bool) -> int:
    task = ctx.board.task(task_id)
    if task.status != IN_REVIEW:
        raise QworkError(f"{task.id} is '{task.status}'; only '{IN_REVIEW}' tasks can be finished")

    repo_path = ctx.workspace / task.repo
    if not repo_path.is_dir():
        raise QworkError(f"{task.id}: repository {task.repo} is not cloned at {repo_path}")
    git = Git(repo_path, ctx.run)
    if not git.branch_exists(task.branch):
        raise QworkError(f"branch {task.branch} does not exist in {task.repo}")

    wt = worktree_path(ctx.workspace, task)
    if wt.exists() and Git(wt, ctx.run).is_dirty(include_untracked=True):
        raise QworkError(f"{wt.relative_to(ctx.workspace)} has uncommitted or untracked files")
    if git.is_dirty():
        raise QworkError(f"{task.repo} has uncommitted changes")

    git.checkout("development")
    sha = git.merge_no_ff(task.branch, f"Merge {task.branch} into development")
    if wt.exists():
        git.remove_worktree(wt)
    if push:
        git.push("origin", "development")

    ctx.board.set_status(task, DONE)
    pushed = " and pushed" if push else " (not pushed)"
    ctx.board.close(task, f"Merged `{task.branch}` into `development` as {sha}{pushed}.")
    print(f"{task.id}: merged {task.branch} into development ({sha[:10]}){pushed}; marked {DONE}", file=ctx.out)
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project tools pytest tools/tests -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tools/src/qwork/finish.py tools/tests/test_finish.py
git commit -m "Add work finish

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Live verification and workflow docs

**Files:**
- Modify: `README.md` (new "Working with AI agents" section after "Board Status Workflow")
- Modify: `AGENTS.md` only if the Antigravity check below fails

**Interfaces:**
- Consumes: the complete `./work` CLI (Tasks 1–8).
- Produces: documented, verified workflow.

- [ ] **Step 1: Read-only checks against the real board**

```bash
./work --help
./work board show Q-016
./work start Q-016 --agent claude --dry-run
```

Expected: help lists `start`, `finish`, `board`; `board show` prints real data; the dry run refuses with `Q-016 is 'Blocked'; only 'Todo' or 'In Progress' tasks can be started` and exit code 1. If a `Todo` task exists on the board, also run `./work start <ID> --agent codex --dry-run` and read the rendered prompt.

- [ ] **Step 2: Confirm the `In Review` option exists**

```bash
gh project field-list 2 --owner GuilhermeFortuna --format json | jq -r '.fields[] | select(.name=="Status") | .options[].name'
```

Expected: includes `In Review`. If not, remind the human (Task 1 Step 9) and continue.

- [ ] **Step 3: Confirm Antigravity loads `AGENTS.md`**

```bash
agy -p "Without reading any files, quote the first markdown heading of your workspace instructions. Reply with only that line."
```

Expected: `# Q workspace — agent instructions`. If Antigravity does not see it, create `GEMINI.md` containing `@AGENTS.md`, rerun the check, add `GEMINI.md` to the tracked files list in spec §1.1, and commit both.

- [ ] **Step 4: Confirm interactive launch through `uv` keeps the terminal**

Ask the human to run, in their own terminal, a dry run on any `Todo` task, then a real `./work start <ID> --agent claude` if they want to begin work. Expected: the agent's interactive UI takes over the terminal (keyboard input works). If `uv run` breaks TTY input, change the last line of `work` to run the installed script directly:

```bash
uv sync --quiet --project "$root/tools"
exec "$root/tools/.venv/bin/qwork" "$@"
```

- [ ] **Step 5: Document the workflow in `README.md`**

Insert after the Board Status Workflow table:

````markdown
### Working with AI agents

Agents are launched from the workspace root with `./work` (requires `uv` and an authenticated `gh`):

```bash
./work start Q-010 --agent claude              # Todo → In Progress, branch Q-010-…, launch Claude Code
./work start Q-010 --agent codex --effort high --worktree
./work start Q-010 --agent cursor --model sonnet-5 --effort high
./work start Q-010 --agent antigravity --dry-run  # print the prompt, change nothing
./work board show Q-010
./work finish Q-010 [--push]                    # In Review → merge --no-ff into development → Done
```

Agents finish by running `./work board set <ID> in-review -m "…"` (or `blocked`). Task branches
stay local and are kept after `finish`. Workspace rules for agents live in [`AGENTS.md`](AGENTS.md).
````

- [ ] **Step 6: Full test run and commit**

Run: `uv run --project tools pytest tools/tests -q`
Expected: all pass.

```bash
git add README.md AGENTS.md
git commit -m "Document the agent task workflow

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```
