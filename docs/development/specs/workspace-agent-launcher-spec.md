# Workspace meta-repo and agent task launcher — spec

**Status:** Approved 2026-09-14
**Scope:** the `q/` workspace directory (not any single Q repository)

## Goal

Let AI coding agents pick up tasks from the
[Q project board](https://github.com/users/GuilhermeFortuna/projects/2) with one
command, work on them in an isolated local branch, and keep the board status
current without manual updates, while the human keeps control of plan approval
and merges.

## Non-goals

- Pull requests per task. PRs are only for `development` → `main` merges and stay manual.
- Pushing task branches. Task branches stay local.
- Headless or unattended agent runs. Sessions are interactive.
- Changing the board's field configuration through the API.

## Part 1 — Workspace foundation

### 1.1 `q/` becomes a meta-repo

`q/` is initialised as a git repository that tracks only workspace-level files.
The sibling repositories stay independent clones and are ignored:

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
```

Because ripgrep-based agent search tools honour `.gitignore`, a `q/.ignore` file re-includes
the five repositories (`!/q_backend/` …); each repository's own `.gitignore` still applies.

Tracked: `README.md`, `AGENTS.md`, `CLAUDE.md`, `docs/`, `q_workspace.code-workspace`,
`q-workspace/` (symlinks and `.serena/project.yml`), `work`, `tools/`.

### 1.2 Agent instructions

- `q/AGENTS.md` is the canonical instruction file. It covers:
  - repository map and dependency direction (`q_contracts` → pinned `CONTRACTS_REV` → consumers; `make contracts-check`);
  - `q-workspace/` is a symlink view for Serena only, and edits always go through the real repo paths;
  - before working in a repo, read its own `AGENTS.md`/`README.md`;
  - the board workflow and status rules (section 2.2);
  - agents never push, merge, check out `development`, or close issues;
  - use the `gh` CLI for GitHub operations.
- `q/CLAUDE.md` contains only `@AGENTS.md`. Codex CLI, Cursor CLI and Antigravity CLI
  read `AGENTS.md` natively (Antigravity also references `GEMINI.md`; no `GEMINI.md` is
  added, to avoid loading instructions twice — confirmed against `agy` during implementation).

### 1.3 Serena workspace

The symlinks in `q/q-workspace/` are replaced with:

```
q_backend   -> ../q_backend
q_contracts -> ../q_contracts
q_core      -> ../q_core
q_frontend  -> ../q_frontend
q_terminal  -> ../q_terminal
```

The obsolete `backend`, `desktop`, `frontend`, `shared` and `worker` links are removed.
`.serena/project.yml` is reviewed for paths referring to the old link names.

### 1.4 Board status `In Review`

- The human adds an `In Review` option to the board's `Status` field in the GitHub UI,
  ordered between `In Progress` and `Done`. This is not done through the API,
  because replacing single-select options can reset existing item values.
- `README.md` "Board Status Workflow" table gains:
  `In Review` — implementation committed on a local task branch, checks run,
  awaiting human review and merge.

## Part 2 — `qwork` launcher

### 2.1 Layout

```
q/
├── work                       # shim: exec uv run --project "$(dirname "$0")/tools" qwork "$@"
└── tools/                     # uv project, package "qwork", stdlib only at runtime
    ├── pyproject.toml         # [project.scripts] qwork = "qwork.cli:main"; dev dep: pytest
    ├── prompts/implement.md
    ├── src/qwork/
    │   ├── cli.py             # argparse entry point and subcommands
    │   ├── runner.py          # single subprocess wrapper for gh/git
    │   ├── board.py           # board lookup, status updates, issue comments/close
    │   ├── repo.py            # task files, branch/worktree, merge
    │   ├── agents.py          # agent command construction and effort validation
    │   └── template.py        # prompt rendering
    └── tests/
```

The shim works from any current directory, but agents and the launcher treat `q/`
(the shim's directory) as the workspace root.

### 2.2 Status transitions

| Transition | Performed by | Via |
|---|---|---|
| `Blocked` → `Todo` | human | GitHub UI only |
| `Todo` → `In Progress` | launcher | `work start` |
| `In Progress` → `In Review` | agent | `work board set <ID> in-review -m …` |
| `In Progress` → `Blocked` | agent | `work board set <ID> blocked -m …` |
| `In Review` → `Done` | human | `work finish` |

`board set` accepts only `in-review` and `blocked`, and only from `In Progress`.
Any other target is rejected with a non-zero exit.

### 2.3 Task resolution

A task ID matches `^Q-\d{3}$`. Resolution:

1. List items of project 2 (owner `GuilhermeFortuna`) with `gh project item-list --format json`
   and select the single item whose title starts with `<ID> `. Zero or multiple matches is an error.
2. From the item: issue repository and number, issue URL, `Status`, `Depends on`
   (comma/space separated IDs; empty if unset), project item ID.
3. Local repo path: `q/<repository name>`. Missing directory is an error.
4. Spec: exactly one file matching `<repo>/docs/development/specs/<ID>-*-spec.md`.
   Plan: exactly one matching `<repo>/docs/development/plans/<ID>-*-plan.md`.
   Missing or ambiguous is an error.
5. Branch name: `<ID>-<slug>`, where slug is the issue title after the ID and dash,
   lowercased, non-alphanumerics collapsed to `-`, trimmed of `-`.
6. Project ID, `Status` field ID and option IDs are resolved at runtime with
   `gh project view` / `gh project field-list` (not hard-coded).

### 2.4 `work board show <ID>`

Prints the resolved task: ID, title, status, repo, issue URL, dependencies with
their statuses, spec path, plan path, branch name, and whether the branch and
worktree exist locally.

### 2.5 `work board set <ID> in-review|blocked [-m MESSAGE]`

Validates the transition (2.2), sets the status, and if `-m` is given posts it as a
comment on the issue. `blocked` requires `-m`.

### 2.6 `work start <ID> --agent claude|codex|cursor|antigravity [--effort E] [--model M] [--worktree] [--dry-run]`

**Arguments**

- `--agent` is required.
- `--model` is optional and passed through to the agent's model flag.
- `--effort` defaults to `medium`. Support differs per agent; validation happens before
  any side effect:

  | Agent | Executable | Effort values | How effort is applied |
  |---|---|---|---|
  | claude | `claude` | `low medium high xhigh max` | `--effort E` |
  | codex | `codex` | `minimal low medium high xhigh` | `-c model_reasoning_effort=E` |
  | cursor | `agent` | `low medium high xhigh max` | appended to the model as `--model 'M[effort=E]'`; requires `--model` |
  | antigravity | `agy` | `low medium high` | `--effort E` |

  - An explicitly passed `--effort` that the agent cannot apply (cursor without `--model`;
    a value outside the agent's list) is an error.
  - The implicit default is skipped with a one-line notice when it cannot be applied.
- Without `--worktree`, the task branch is checked out in the repo's main checkout (branch mode).

**Preconditions** (all checked before any side effect)

1. Task resolves (2.3).
2. Status is `Todo`, or `In Progress` (resume). Anything else is an error.
3. Every dependency resolves and is `Done`.
4. The agent executable is on `PATH`.
5. Branch mode: the repo's main checkout has no uncommitted changes to tracked files.
   Worktree mode: if the worktree already exists it must be on the task branch.
6. `git fetch origin development` runs; if local `development` is behind
   `origin/development`, print a warning (not an error).

**Effects**

1. Branch: if `<branch>` does not exist, create it from local `development`.
   If it exists and status is `Todo`, error (stale branch; the human decides).
   If it exists and status is `In Progress`, reuse it (resume).
2. Working directory:
   - branch mode: `git checkout <branch>` in `q/<repo>`; workdir = `q/<repo>`;
   - worktree mode: `git worktree add q/.worktrees/<repo>/<branch> <branch>` unless it
     already exists; workdir = that path.
3. Render `prompts/implement.md` (2.8).
4. Set status to `In Progress` (no-op when resuming).
5. `os.execvp` the agent with the current directory set to `q/`:
   - claude: `claude [--model M] --effort E <prompt>`
   - codex: `codex [-m M] -c model_reasoning_effort=E <prompt>`
   - cursor: `agent [--model 'M[effort=E]'] <prompt>`
   - antigravity: `agy [--model M] --effort E -i <prompt>` (interactive session seeded with the prompt)

   Flags were read from the installed CLIs (`agy` 1.2.2, Cursor `agent` 2026.09.02) and are
   re-verified during implementation; each
   agent's command construction is covered by a unit test.

**`--dry-run`** runs the resolution and all preconditions, prints the planned effects
and the rendered prompt, and changes nothing (no branch, worktree, status or launch).

### 2.7 `work finish <ID> [--push]`

**Preconditions**

1. Task resolves; status is `In Review`.
2. Branch `<branch>` exists.
3. If a worktree for the branch exists, it has no uncommitted changes to tracked files.
4. The repo's main checkout has no uncommitted changes to tracked files.

**Effects, in order**

1. In `q/<repo>`: `git checkout development`, then `git merge --no-ff <branch>`.
   On failure: `git merge --abort`, report, exit non-zero. No further effects.
2. Remove the worktree if present (`git worktree remove`). The branch is kept.
3. With `--push`: `git push origin development`.
4. Set status to `Done`.
5. Close the issue with a comment naming the merge commit SHA and branch.

### 2.8 Prompt template

`prompts/implement.md` uses `string.Template` placeholders:
`$id $title $repo $issue_url $spec $plan $workdir $branch $resume $repo_agents`
(`$repo_agents` lists whichever of the repo's `AGENTS.md`/`CLAUDE.md`/`README.md` exist;
`$resume` is a note that previous work exists on the branch, or empty).
Unknown or missing placeholders are an error.

The template instructs the agent to:

1. Read `q/AGENTS.md`, the repo instruction files, the issue, the spec and the plan.
2. Work only in `$workdir` on `$branch`; follow the plan task by task; commit locally
   with focused commits.
3. Run the repository's documented checks; fix failures caused by the change.
4. Never push, merge, check out `development`, or close the issue.
5. On completion: `./work board set $id in-review -m "<acceptance summary: what was
   done, checks run and results, open follow-ups>"`.
6. If blocked: `./work board set $id blocked -m "<reason>"` and stop.

## Part 3 — Error handling

- Every failure prints one clear line to stderr and exits non-zero.
- All preconditions run before any git or board side effect.
- `gh` and `git` calls go through `runner.run(args, cwd)`, which raises a typed error
  carrying the command and its stderr.

## Part 4 — Testing

- **Unit** (fake runner with canned `gh` JSON): task resolution, dependency checks,
  transition rules, effort validation, branch slugging, template rendering and
  missing-placeholder errors, agent command construction, `--dry-run` has no side effects.
- **Git integration** (temporary repos with a bare `origin`): branch creation from
  `development`, resume on existing branch, stale-branch error, dirty checkout refusal,
  worktree creation, `finish` merge with `--no-ff`, conflict → abort with no board calls,
  worktree removed and branch kept.
- Run with `uv run --project tools pytest`.

## Build order

1. Foundation (Part 1), except the board UI change, which the human does.
2. `runner`, `board`, `board show/set`.
3. `repo`, `template`, `agents`, `start`.
4. `finish`.
