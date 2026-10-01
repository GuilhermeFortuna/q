# Q-078: Launcher respects saved terminal setup

**Status:** written spec and plan awaiting human review; status of record is the [Q project board](https://github.com/users/GuilhermeFortuna/projects/2).
**Batch:** 13 — persistent terminal setup and live market analysis
**Depends on:** Q-077
**Implementation plan:** [Plan](../plans/Q-078-launcher-respects-saved-terminal-setup-plan.md)

## Purpose

Let ./dev reopen the terminal’s saved chart target while retaining explicit startup overrides.

## Current system

launch_terminal in dev injects and exports PETR4/M1 on every launch. Q-077 distinguishes explicit overrides from fallback config; injected defaults would otherwise override the saved target.

## Required behavior

- Remove synthesized Q_TERMINAL_SYMBOL and Q_TERMINAL_TIMEFRAME values from launch_terminal. Preserve a caller-supplied nonempty value unchanged. An unset or empty target variable is absent to the terminal.
- Preserve Q_TERMINAL_API_BASE behavior and live/research API isolation. The terminal’s own documented defaults serve first launch; do not add workspace-file parsing to the shell launcher.
- Apply this behavior to ./dev live, all/default, legacy up profiles and interactive shell paths through the shared launch handler. An already-running terminal retains its target; no implicit retarget/relaunch.
- Document target precedence from Q-077 and examples for saved restoration and explicit overrides. Update the launcher section of README to describe first-run terminal defaults accurately after inspecting Q-077’s final values.

## Interfaces and ownership

dev remains the only lifecycle entrypoint; q_terminal owns its saved UI state.
Change launch_terminal and extend tools/tests/test-dev. No new flags, configuration file, backend command or lifecycle state is added.

## Acceptance criteria

1. The mocked launch captures no target override when caller variables are unset or empty, and captures explicit symbol/timeframe byte-for-byte when provided.
2. API base, pidfile reuse, background launch and service lifecycle behavior remain covered and unchanged.
3. Default/all, live, legacy up and interactive shell dispatch share the tested launch path.
4. Bash syntax and focused mocked launcher checks pass without Docker, GPU, Wine or a desktop.

## Implementation boundary

This issue authorizes only its listed deliverable after written-plan approval and
`./work start Q-078 --agent <agent> --worktree`. Dependencies must be Done.
Preserve the existing execution controls and research/operations ownership boundaries.
No live-order activation, new backend-process ownership or unrelated refactoring.
Use generated contracts and commit/tag pins; never edit vendored code by hand.
