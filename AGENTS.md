# Q workspace — agent instructions

You are in `q/`, the workspace root of the Q quantitative trading platform. `q/` is a
small meta-repo; the product code lives in independent git repositories inside it.

## Public repository quality

Treat every Q repository as public, production-quality work that prospective employers may
review. Use conventional, maintainable solutions with clear ownership and complete, accurate
documentation. Keep specs, plans, code, CI, and GitHub issues consistent and reviewable;
remove temporary scaffolding and avoid machine-specific shortcuts or unconventional
workarounds. When a required tool or credential is unavailable, report the blocker and
resume through the documented workflow once it is restored.

## Repositories

| Path | Role |
|---|---|
| `q_contracts/` | Source of truth for versioned schemas and wire contracts (control API, stream envelope, Wine edge, lake manifests) and their code generators |
| `q_backend/` | FastAPI control API, Dramatiq workers, PostgreSQL ledger/outbox, Redis Streams (Python) |
| `q_core/` | Rust workspace of shared deterministic primitives, bound to Python (PyO3) and Qt (cxx-qt) |
| `q_frontend/` | Tauri 2 + React 19 research desktop UI |
| `q_terminal/` | Qt 6 / QML live trading and operations terminal |
| `q_strategies/` | Private research strategies: one self-contained `ResearchStrategy` module per strategy |

- `q_strategies` is the one private repository. The author's trading strategies, and ports of
  them, live there and never in the public repositories. It has a single `main` branch, no CI
  and no board tasks; read its `README.md` before changing it.
- Each repository has its own history, CI, `Makefile` and branches (`development`, `main`,
  sometimes `staging`). Run git commands inside the repository or worktree you are
  changing (e.g. `git -C q_backend ...`), never in the `q/` meta-repo itself.
- Run only the checks, tests and builds needed to verify your change: the tests covering
  the code you touched, plus format and lint for the affected crate or package. Do not run
  a repository's full `make check`, `make ci` or complete test suite unless the change is
  broad enough to need it; the full CI pipeline runs before anything is pushed.
- Local CI in each child repo automatically enters the host user `ci.slice` (and CI Docker
  under `ci-docker.slice` when applicable) when those slices exist. When you do run a repo's
  CI command, invoke it as documented — do **not** wrap it in `systemd-run`, `ci-run`, or
  `--cgroup-parent`. Remote CI is unaffected (slices are absent on hosted runners).
- Put disk-heavy build output on the NVMe build disk at `/mnt/build`, never on the root
  disk. Main checkouts already link their Rust `target/` there. In a new worktree, before
  the first cargo build, create `/mnt/build/targets/<repo>-<branch-slug>` and symlink
  `target` to it; create Python environments with
  `UV_PROJECT_ENVIRONMENT=/mnt/build/venvs/<name>`. `/mnt/build` holds only rebuildable
  data: delete a worktree's target directory and environment when you remove the worktree.
- `./work` lives at the workspace root. Run it from there, or by its absolute path
  (e.g. `/path/to/q/work`), not from inside a task's repository or worktree.
- `./dev` is the canonical local development launcher for the Q platform. It supports:
  - `./dev` or `./dev all`: starts both Live and Research stacks and opens both desktop UIs.
  - `./dev live`: starts the full live execution profile and launches `q_terminal`.
  - `./dev research [opts]`: starts Research backend and launches Tauri research desktop UI (`--host` default, `--container`, `--rebuild`).
  - `./dev gateway`: starts only the MT5 terminal and data gateway for scripts; waits for MT5 connectivity. Default URL: `http://127.0.0.1:18812`.
  - `./dev down [live|research|all]`: selectively stops stacks (default `all`). Stopping live retains the shared MT5 gateway if Research is running and using it.
  - `./dev status`: concise overview of both stacks, APIs, workers, and desktop UIs.
  - `./dev logs <service>`: follows logs by alias (unqualified for live, `research:<svc>` for research).
  - `./dev restart <service>`: restarts a service by alias.
  - `./dev up [terminal|execution|full]`: legacy profile start.
  - Persistent lifecycle: launcher commands return after launching desktop UIs; closing a UI window or pressing Ctrl+C does not stop backend services. Services stay running until explicitly stopped via `./dev down [live|research|all]`.
- `./research` is a backward-compatible shim forwarding directly to `./dev research "$@"`.
  - Default (`--host`): containerized Postgres and Redis only; the API and
    Dramatiq worker run from `q_backend/.venv`, and torch uses the host GPU
    directly. Nothing is built, exported, or downloaded — the NVIDIA Container
    Toolkit is not required.
  - `--container`: API and worker in containers on the shared `q-backend:dev`
    image; warm starts reuse it when image-defining inputs match, and
    `--rebuild` forces one rebuild. Requires the NVIDIA Container Toolkit and
    costs roughly 6 GB of image plus BuildKit cache on a first build. After a
    build the launcher caps retained BuildKit cache at
    `Q_RESEARCH_BUILD_CACHE_MAX` (default `4GB`); `off` disables the cap. That
    bounded prune never touches images, containers, or named volumes.
- Contracts flow one way: `q_contracts` → consumers pin a commit in `CONTRACTS_REV` and vendor
  generated code. Never hand-edit vendored contract code; verify with `make contracts-check`
  in the consumer.
- Before working in a repository, read its `AGENTS.md` (if present) and `README.md`. They
  contain repo-specific commands and caveats (for example, `q_frontend` tests need
  `TZ=America/Sao_Paulo`).
- `q-workspace/` is a symlink view for the Serena code-navigation server. Never edit files
  through it; use the real repository paths.
- `.worktrees/` holds task worktrees created by `./work start --worktree`.
- Human review uses `./work inspect <ID>` after `In Review`: normal checkouts switch to
  the task branches, while task worktrees remain temporarily detached. Stop stacks with
  `./dev down` and close desktop UIs before inspect or restore; then run `./dev` normally.
  `./work inspect --restore` restores previous checkout states without GitHub access.
  If inspection switches `q` itself to older launcher code, use the printed recovery
  command at `.worktrees/inspect-runner/work` for restore or finish.
  Alternatively, `./work finish <ID>` merges directly and clears the inspection session.
  Only one inspection is active at a time; agents must leave its checkout state alone.
- The `q/` meta-repo itself tracks only workspace files (`AGENTS.md`, `README.md`, `docs/`,
  `tools/`, `work`, `dev`, `research`, `q-workspace/`).

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
| `Done` | Merged into `development`, and in a repository with a `RELEASING.md` (`q_core`) released as a pushed `vYYYY.MM.DD` tag (suffixed `.2`, `.3`, … for a second release the same day) | `./work finish` (human) |

### Rules for agents

- Work only on the task you were launched for. If asked to implement a board task that is not
  already `In Progress`, ask the human to launch it with `./work start <ID> --agent <agent>`.
- Read task metadata with `./work board show <ID>`. `./work inspect` is for human runtime review.
- When the work is complete and checks pass:
  `./work board set <ID> in-review -m "<what was done; checks run and results; open follow-ups>"`
- When you cannot continue:
  `./work board set <ID> blocked -m "<what blocks you and what is needed>"`, then stop.
- Never push, merge, check out `development`/`main`/`staging`, close issues, or change board
  statuses any other way (no `gh project item-edit`, no web UI).
- A task that changes more than one repository is executed in each of them: create the task
  branch from `development` in every repository it changes, do the work and checks there, and
  report all of them in one board message. Launch instructions give the exact commands.
- Commit on the task branch with focused commits that follow the repository's conventions.
- Use the `gh` CLI for GitHub operations.
- Keep task specs and plans lean. Include only checks needed to verify the changed
  behavior; prefer focused mocks for launcher work. Do not require full CI,
  GPU, Wine, Docker, or desktop runs without a concrete task-specific need.
- Run only the checks your change needs (see the workspace rules above) and report which
  checks you ran.
