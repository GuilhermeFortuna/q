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
  sometimes `staging`). Run git commands inside the repository or worktree you are
  changing (e.g. `git -C q_backend ...`), never in the `q/` meta-repo itself.
- Local CI in each child repo automatically enters the host user `ci.slice` (and CI Docker
  under `ci-docker.slice` when applicable) when those slices exist. Invoke each repo's
  normal canonical CI command only — do **not** wrap it in `systemd-run`, `ci-run`, or
  `--cgroup-parent`. Remote CI is unaffected (slices are absent on hosted runners).
- `./work` lives at the workspace root. Run it from there, or by its absolute path
  (e.g. `/path/to/q/work`), not from inside a task's repository or worktree.
- `./research` starts the Research/Backtests stack (containerized `q_backend` +
  host Tauri UI) and tears it down on Ctrl+C. Prefer it over manual compose/UI
  steps when iterating on backtests. Use `./research --rebuild` to force an image
  rebuild; warm starts reuse `q-backend:dev` when image-defining inputs match.
  Research requires NVIDIA Container Toolkit and fail-closes if CUDA is unavailable.
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
| `Done` | Merged into `development`, and in a repository with a `RELEASING.md` (`q_core`) released as a pushed `vYYYY.MM.DD` tag | `./work finish` (human) |

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
