# Q-071 — Interactive Dev Shell Implementation Plan

> **For agentic workers:** Implement this plan with focused commits. Use mocked command execution; no full stack launch is needed.

**Goal:** Add `./dev shell` as a small interactive interface over Q-070's noninteractive commands.

**Architecture:** Add a prompt loop that parses a limited command vocabulary and dispatches to the same `./dev` command path. It holds no independent stack state; status and lifecycle always come from the underlying launcher.

**Tech Stack:** Bash and the existing Q-070 launcher; no new runtime dependency.

**Spec:** `docs/development/specs/Q-071-interactive-dev-shell-spec.md`

## Implementation

- [ ] **Add the prompt.** Handle `shell` in `dev`; read one line at a time, parse only the spec's commands and mode flags, and dispatch through the existing CLI handler. Start with no side effects. Keep the prompt active after a command error, and show `help` and unknown-command messages.
- [ ] **Handle interaction boundaries.** Make `exit`, `quit`, EOF and idle Ctrl+C leave services running. Allow Ctrl+C during `logs` to return to the prompt. Ensure desktop UIs started by `up` do not block it.
- [ ] **Document the shell.** Add short examples to `README.md` and `./dev --help`, including `exit` versus `down` behavior.

## Minimal verification

- [ ] Add one mocked stdin transcript to the workspace launcher harness covering `up`, `status`, `down`, error recovery and exit without teardown. Add a focused Ctrl+C log-follow check if the transcript cannot express it.
- [ ] Run the mocked shell check and `bash -n dev`; do not run real GPU, Wine, Docker or desktop checks for this prompt layer.

## Handoff

Keep Q-071 `Blocked` until the human approves the plan and Q-070 is `Done`. Then launch it through `./work start Q-071 --agent <agent>`.
