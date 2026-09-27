# Q-070 — Unified development launcher — spec

**Status:** Awaiting plan approval
**Owner:** `q/` workspace repository

## Goal

Use one workspace command to start, inspect and stop the live and Research stacks independently or together. Preserve the existing isolation between their databases, Redis instances, APIs and data directories, and make startup failures actionable.

## Command contract

| Command | Behavior |
|---|---|
| `./dev`, `./dev all` | Start both stacks and both desktop UIs. |
| `./dev live` | Start the full live execution profile and Qt terminal. |
| `./dev research [--host\|--container] [--rebuild]` | Start Research backend and UI; host mode is the default. `--rebuild` requires container mode. |
| `./dev down live\|research\|all` | Stop only the selected stack; `all` stops both. |
| `./dev status` | Show both stacks, including APIs, workers and desktop UIs. |
| `./dev logs <service>` | Follow a service log; `live:<service>` and `research:<service>` disambiguate shared names. Unqualified existing aliases continue to mean live. |
| `./dev restart <service>` | Restart an existing managed service; use the same qualified aliases. |
| `./dev --help` | Show the command contract, modes and lifecycle behavior. |

`./dev all` uses Research host mode unless `Q_RESEARCH_MODE=container` is set. The existing `Q_RESEARCH_*`, `Q_DEV_*` and Research UI variables remain usable. `./research` becomes a compatibility shim for `./dev research`, including its current mode flags. The existing `./dev up terminal|execution|full`, `./dev down`, `./dev status`, `./dev logs` and `./dev restart` forms remain accepted; bare `./dev down` means `all`. Document the new persistent lifecycle prominently because `./research` currently tears itself down on exit.

Commands return after starting desktop UIs. Closing a UI or pressing Ctrl+C while a launcher command is running does not tear down either backend. Only `down` stops services. Repeating a start command must not duplicate managed processes or windows. A failed start returns nonzero and reports the failing prerequisite or service, its relevant log location, and what remains running. A start failure must not stop a previously running other stack.

## Runtime ownership

- Live keeps its `q-dev` Compose project, ports 5434/6380/8000, `q_backend/data/`, systemd user units, and current execution readiness/degraded reporting.
- Research keeps its `q-research` Compose project, ports 5435/6381/8001, `q_backend/data/research/`, CUDA preflight and host/container choices. Host API, worker and outbox relay must remain supervised after `./dev` exits; container mode still reuses the fingerprinted image and bounded BuildKit cache behavior.
- The Research UI continues to point at API port 8001 with MSW disabled; the Qt terminal continues to point at live API port 8000. The launcher owns each UI process separately and can stop it without affecting the other.
- The MT5 terminal and gateway are shared systemd services. Research may use/start the local gateway in host mode, but `down research` never stops shared MT5 services. `down live` keeps the gateway/terminal running if Research is using the local gateway. `down all` stops them. The execution edge and worker belong only to live.
- Preflight checks run for the selected stack before changing it: required programs, configured port ownership and Research CUDA access. The selected stack's readiness and failure messages identify the service and log command/path. Remote gateways are never stopped by the launcher.

## Board launcher bootstrap

`./work start` currently resolves an issue repository under `q/<name>` and requires a `development` branch. For workspace-owned issues in `GuilhermeFortuna/q`, it must resolve to the workspace root while preserving existing child-repository behavior. The first workspace task must be launched manually until this bootstrap is installed. A local `development` branch for `q/` and committed task files are prerequisites for subsequent `./work start` sessions; the human retains approval and branch integration.

## Acceptance

- Mocked launcher checks exercise `live`, `research`, `all`, default `all`, selective `down`, repeated starts, conflicting ports, failed readiness, host/container mode selection and shared gateway retention. No real GPU, Wine, Docker containers or desktop apps are required for this task's automated checks.
- The existing Research image/CUDA regression harness remains green after adapting its command entry point. Shell syntax checks cover edited shell files.
- Documentation states the new commands and the change from Research's Ctrl+C cleanup to explicit `down`.

**Out of scope:** rewriting the backend, changing trading safety logic, merging Research and live data, changing production deployment, and implementing the interactive shell (Q-071).
