# `./work` — agent task launcher

`./work` starts an AI coding agent on a task from the
[Q project board](https://github.com/users/GuilhermeFortuna/projects/2), keeps the card's status
up to date, and merges the finished work into `development` once you approve it.

- [Requirements](#requirements)
- [The workflow at a glance](#the-workflow-at-a-glance)
- [`work start`](#work-start) — start or resume a task with an agent
- [`work board show`](#work-board-show) — inspect a task
- [`work board set`](#work-board-set) — status updates (used by agents)
- [`work finish`](#work-finish) — merge a reviewed task and mark it Done
- [Agents, effort and models](#agents-effort-and-models)
- [Branch mode vs worktree mode](#branch-mode-vs-worktree-mode)
- [What the agent is told](#what-the-agent-is-told)
- [Troubleshooting](#troubleshooting)

## Requirements

| Requirement | Why |
|---|---|
| [`uv`](https://docs.astral.sh/uv/) | Runs the tool (`tools/`) — no manual install step |
| `gh`, logged in with the `project` scope | Reads and updates the board and issues |
| The task's repository cloned in `q/` (e.g. `q/q_backend`) | Branches and worktrees are created there |
| A local `development` branch in that repository | Task branches start from it and merge back into it |
| The agent CLI on `PATH`: `claude`, `codex`, `agent` (Cursor) or `agy` (Antigravity) | The agent that does the work |
| An `In Review` option on the board's Status field | Agents move finished tasks there |

Run it from the workspace root (`./work …`) or by absolute path (`/home/gui/projects/q/work …`)
from anywhere.

## The workflow at a glance

```
 you                               agent                              you
 ───                               ─────                              ───
 (GitHub UI) Blocked → Todo
 ./work start Q-010 --agent …  →   Todo → In Progress
                                   works on branch Q-010-…
                                   commits locally (never pushes)
                                   ./work board set Q-010 in-review → In Review
                                                                      review the branch
                                                                      ./work finish Q-010 → Done
```

| Status | Set by | How |
|---|---|---|
| `Blocked` → `Todo` | you | GitHub UI only (this is plan approval) |
| `Todo` → `In Progress` | `./work start` | automatically |
| `In Progress` → `In Review` | the agent | `./work board set <ID> in-review -m "…"` |
| `In Progress` → `Blocked` | the agent | `./work board set <ID> blocked -m "…"` |
| `In Review` → `Done` | you | `./work finish <ID>` |

Task IDs always look like `Q-NNN` (e.g. `Q-010`).

---

## `work start`

Checks that a task can be started, prepares its branch, sets it to `In Progress`, and launches
the agent in your terminal with a prompt that points it at the task's spec and plan.

```
./work start ID --agent AGENT [--effort EFFORT] [--model MODEL] [--worktree] [--dry-run]
```

| Parameter | Required | Default | Description |
|---|---|---|---|
| `ID` | yes | — | Board task ID, e.g. `Q-010` |
| `--agent` | yes | — | `claude`, `codex`, `cursor` or `antigravity` |
| `--effort` | no | `medium` | Reasoning effort; allowed values depend on the agent ([table](#agents-effort-and-models)) |
| `--model` | no | agent's default | Model name passed to the agent |
| `--worktree` | no | off | Work in `q/.worktrees/<repo>/<branch>` instead of switching the repo's own checkout ([details](#branch-mode-vs-worktree-mode)) |
| `--dry-run` | no | off | Run every check, then print what would happen and the full prompt. Changes nothing. |

### Examples

```bash
./work start Q-010 --agent claude                                  # Claude Code, effort medium
./work start Q-010 --agent claude --effort high --model opus
./work start Q-010 --agent codex --effort xhigh --worktree
./work start Q-010 --agent cursor --model sonnet-5 --effort high   # Cursor needs --model to use --effort
./work start Q-010 --agent antigravity --dry-run                   # preview only
```

### What it checks (before changing anything)

1. The task is on the board and its status is **`Todo`** (new start) or **`In Progress`** (resume).
2. Every task in its **Depends on** field is **`Done`**. `In Review` doesn't count, because that
   work isn't merged yet.
3. The repository is cloned, and exactly one spec
   (`docs/development/specs/<ID>-*-spec.md`) and one plan (`docs/development/plans/<ID>-*-plan.md`) exist.
4. The agent's executable is on `PATH`.
5. The effort/model combination is valid for the agent.
6. **Branch mode:** the repository has no uncommitted changes to tracked files.
   **Worktree mode:** if the worktree already exists, it is on the task branch.
7. For a **`Todo`** task, the task branch must **not** exist yet. A leftover branch is reported
   and you decide what to do with it.

It also runs `git fetch origin development` and warns (without stopping) if your local
`development` is behind.

### What it does

1. Creates branch `<ID>-<title-slug>` from local `development` (e.g. `Q-010-transactional-outbox`),
   unless it's resuming.
2. Checks the branch out in the repository, or with `--worktree` creates the worktree.
3. Sets the task to `In Progress` (skipped when resuming).
4. Launches the agent from the workspace root with the rendered prompt, in a clean environment
   (the launcher's own Python virtualenv is removed from `PATH`).

### Resuming

Running `start` again on an `In Progress` task reuses the existing branch/worktree, leaves the
status alone, and tells the agent to review what earlier sessions committed before continuing.
You can resume with a different agent or effort.

### Dry-run output

```
Dry run — no changes made. Would:
  - create branch Q-010-transactional-outbox from development in q_backend
  - check out Q-010-transactional-outbox in q_backend
  - set Q-010 to 'In Progress'
  - launch: claude --effort medium <prompt>

--- prompt ---
You are implementing board task Q-010 — Transactional outbox.
…
```

---

## `work board show`

Prints everything `start` would use for a task. It's read-only.

```
./work board show ID
```

| Parameter | Required | Description |
|---|---|---|
| `ID` | yes | Board task ID |

```
$ ./work board show Q-017
Q-017  Todo
Q-017 — Dataset catalog over the existing lake
issue:    https://github.com/GuilhermeFortuna/q_backend/issues/7
repo:     q_backend
depends:  Q-006 (Done)
spec:     q_backend/docs/development/specs/Q-017-dataset-catalog-over-the-existing-lake-spec.md
plan:     q_backend/docs/development/plans/Q-017-dataset-catalog-over-the-existing-lake-plan.md
branch:   Q-017-dataset-catalog-over-the-existing-lake (not created)
worktree: none
```

---

## `work board set`

Used by **agents** to report the result of their work. It deliberately allows only two changes.

```
./work board set ID {in-review|blocked} [-m MESSAGE]
```

| Parameter | Required | Description |
|---|---|---|
| `ID` | yes | Board task ID |
| `in-review` / `blocked` | yes | New status |
| `-m`, `--message` | for `blocked` | Posted as a comment on the task's issue. For `in-review` it should summarise what was done, checks run and their results, and follow-ups. |

Rules enforced by the tool:

- The task must currently be `In Progress`.
- `blocked` requires `-m` with the reason.
- `Todo` and `Done` can't be set this way. `Todo` is set in the GitHub UI and `Done` only by `finish`.

```bash
./work board set Q-010 in-review -m "Outbox table + relay-safe pruning implemented; make check passes (212 tests); follow-up: index tuning"
./work board set Q-010 blocked -m "Needs the Q-009 replay envelope field that isn't in q_contracts yet"
```

---

## `work finish`

Merges a reviewed task branch into `development`, removes its worktree if it has one, marks the
task `Done`, and closes the issue. **The task branch is kept.**

```
./work finish ID [--push]
```

| Parameter | Required | Default | Description |
|---|---|---|---|
| `ID` | yes | — | Board task ID |
| `--push` | no | off | Push `development` to `origin` after merging |

### What it checks

1. The task is **`In Review`**.
2. The task branch exists.
3. The task's worktree (if any) has no uncommitted **or untracked** files.
4. The repository's checkout has no uncommitted changes to tracked files.

### What it does, in order

1. `git checkout development`, then `git merge --no-ff <branch>`.
   **If the merge fails (e.g. a conflict), it is aborted and nothing else happens.** The board
   isn't touched. Resolve it manually, then re-run.
2. Removes `q/.worktrees/<repo>/<branch>` if it exists.
3. With `--push`: `git push origin development`.
4. Sets the task to `Done`.
5. Closes the issue with a comment naming the branch and merge commit.

If a later step fails after the merge succeeded (e.g. the push is rejected), the task stays
`In Review`. Fix the cause and re-run `./work finish <ID>`. The merge step is then a no-op.

```bash
./work finish Q-010           # merge locally, push later yourself
./work finish Q-010 --push    # merge and push development
```

---

## Agents, effort and models

| `--agent` | Launches | `--effort` values | How effort is passed | `--model` |
|---|---|---|---|---|
| `claude` | Claude Code (`claude`) | `low` `medium` `high` `xhigh` `max` | `--effort E` | `--model M` |
| `codex` | Codex CLI (`codex`) | `minimal` `low` `medium` `high` `xhigh` | `-c model_reasoning_effort=E` | `-m M` |
| `cursor` | Cursor CLI (`agent`) | `low` `medium` `high` `xhigh` `max` | as a model parameter: `--model 'M[effort=E]'` | `--model M` |
| `antigravity` | Antigravity CLI (`agy -i`) | `low` `medium` `high` | `--effort E` | `--model M` |

- An `--effort` value the agent doesn't accept is an error, e.g. `--agent antigravity --effort xhigh`.
- **Cursor** can only apply effort through a model. `--agent cursor --effort high` without
  `--model` is an error. With neither flag, Cursor uses its defaults and `work` prints a notice
  that the default effort wasn't applied.
- Every session is **interactive**: the agent takes over your terminal, and you can watch and steer it.

Agent-specific notes:

- **Codex:** its sandbox asks for approval when the agent runs `./work board set`, which needs
  network access for `gh` and writes `uv`'s cache outside the workspace. Approve it.
- **Cursor:** run `agent login` once before using it.
- **Antigravity:** `agy` does not load `AGENTS.md` automatically. Sessions started through
  `./work` are told to read it; sessions you open yourself are not.

## Branch mode vs worktree mode

| | Branch mode (default) | Worktree mode (`--worktree`) |
|---|---|---|
| Where the agent works | the repository's normal checkout, e.g. `q/q_backend` | `q/.worktrees/<repo>/<branch>` |
| Your checkout | switched to the task branch | untouched (stays on `development` or wherever it was) |
| Requires a clean checkout | yes | no |
| Several tasks in the same repo at once | no, they would fight over one checkout | yes, one worktree per task |
| After `finish` | checkout is left on `development` | worktree removed |

In both modes the branch stays **local**. Review it with normal git, for example
`git -C q_backend log development..Q-010-transactional-outbox` or `git diff development...<branch>`.

## What the agent is told

The prompt template lives at [`tools/prompts/implement.md`](../tools/prompts/implement.md). The
agent is told to:

1. Read `AGENTS.md`, the repository's `AGENTS.md`/`CLAUDE.md`/`README.md`, the issue, the spec and the plan.
2. Work only in its working directory on its branch, and never run git in the `q/` meta-repo.
3. Follow the plan task by task, commit locally, and run the repository's checks.
4. Never push, merge, check out `development`/`main`/`staging`, or close the issue.
5. Finish with `board set … in-review -m "<summary>"`, or `board set … blocked -m "<reason>"` and stop.

Use `./work start <ID> --agent <agent> --dry-run` to see the exact prompt for a task.

## Troubleshooting

Every error is one line starting with `work:` and the command exits with status 1.

| Message | Meaning / fix |
|---|---|
| `Q-010 is 'Blocked'; only 'Todo' or 'In Progress' tasks can be started` | Approve the plan by moving the card to `Todo` in GitHub |
| `Q-011 depends on unfinished tasks: Q-010 (In Review)` | Finish the dependency first (`./work finish Q-010`) |
| `Q-010 is 'Todo' but branch Q-010-… already exists in q_backend; delete or rename it first` | A leftover branch from an earlier attempt. Delete/rename it, or set the task to `In Progress` in GitHub to resume on it. |
| `q_backend has uncommitted changes; commit or stash them, or use --worktree` | Clean the checkout, or run with `--worktree` |
| `agent 'cursor' needs 'agent' on PATH` | Install the agent CLI or fix `PATH` |
| `antigravity does not support effort 'xhigh' (allowed: low, medium, high)` | Pick a value from the [table](#agents-effort-and-models) |
| `cursor applies effort through the model; pass --model with --effort` | Add `--model`, or drop `--effort` |
| `board Status has no 'In Review' option; add it in the GitHub project settings` | Add the option in the GitHub UI (Project → Settings → Status) |
| `no spec matching …` / `2 plan files match …` | The task needs exactly one spec and one plan file with the `<ID>-` prefix |
| `merging Q-010-… failed and was aborted: …` | Merge conflict. Resolve it by hand (or rebase the task branch), then re-run `finish` |
| `work: warning: local development is 3 commit(s) behind origin/development` | Not an error. Consider `git pull` in that repository first. |

For the design and exact rules, see the
[spec](development/specs/workspace-agent-launcher-spec.md).
