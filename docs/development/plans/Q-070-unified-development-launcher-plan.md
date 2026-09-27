# Q-070 — Unified Development Launcher Implementation Plan

> **For agentic workers:** Implement this plan task by task with focused commits. Use the existing mocked launcher harness; do not run full GPU, Wine, Docker or desktop checks solely for this task.

**Goal:** Make `./dev [live|research|all]` the persistent, selective launcher for both stacks.

**Architecture:** Keep the existing live and Research runtime implementations, but put command dispatch and lifecycle ownership behind `./dev`. Extract Research startup/stop helpers from the foreground `./research` script so they can be invoked independently; make `./research` forward its legacy flags. Record and validate host process and UI ownership before status, restart or stop. Reuse existing Compose projects and systemd units.

**Tech Stack:** Bash, Docker Compose, systemd user units, Python host processes, existing mocked shell harness.

**Spec:** `docs/development/specs/Q-070-unified-development-launcher-spec.md`

## Implementation

- [ ] **Bootstrap workspace board tasks.** Update `tools/src/qwork/repo.py` and focused `tools/tests/test_repo.py` cases so the issue repository `q` resolves to the workspace root. Keep child repo resolution unchanged. Document that the human must establish the workspace `development` branch and integrate these approved task files before `./work start` can launch later workspace issues. The first Q-070 agent is launched manually because the existing `./work` cannot resolve this repo yet.
- [ ] **Extract Research lifecycle.** Move reusable Research helpers into `tools/dev/research.sh` and make startup nonblocking. Keep its host/container mode, CUDA preflight, image fingerprint/cache behavior, API/worker/relay processes, UI environment and separate Compose/data settings. Store ownership under `Q_RESEARCH_DATA_DIR` (default `q_backend/data/research/`); validate a recorded process before stopping it so stale PIDs cannot kill unrelated processes. Preserve `tools/tests/test-research` as the regression harness and adapt it to the new entry point.
- [ ] **Unify dispatch and selective lifecycle.** Update `dev` to implement the spec's commands, default `all`, qualified service aliases, and idempotent starts. `all` starts live and Research; if either fails, report both states without tearing down the stack that was already running. Keep MT5 gateway/terminal active when Research is using them. Turn `research` into a compatibility shim. Preserve legacy `./dev up terminal|execution|full` and unqualified live service aliases.
- [ ] **Expose useful status and errors.** Extend `./dev status`, `logs` and `restart` to cover Research Compose and host processes, the two UIs and service readiness. Preflight selected-stack prerequisites and port ownership before startup. Print the failing check, a relevant log command/path and the remaining running state after failure.
- [ ] **Update operator docs.** Replace the two-launcher instructions in `README.md` and `AGENTS.md` with the new command contract, selective `down`, and explicit persistence after UI close/Ctrl+C. Keep Research host/container and CUDA notes accurate.

## Minimal verification

- [ ] Run `bash -n dev research tools/dev/research.sh` and the existing `tools/tests/test-research` harness after adapting it.
- [ ] Add a small mocked command harness for default/all/live/research dispatch, selective stop, repeated start, a port conflict, a failed Research preflight, and gateway retention; run that harness once.
- [ ] Review the resulting help text and docs against the command table in the spec. Do not require a real stack launch or the child repositories' full CI for this workspace-only change.

## Handoff

Keep Q-070 `Blocked` until the human approves this plan. Then the human establishes/updates the `q` repository's `development` branch and launches the bootstrap agent manually. After the `./work` fix lands, Q-071 can use the normal board workflow.
