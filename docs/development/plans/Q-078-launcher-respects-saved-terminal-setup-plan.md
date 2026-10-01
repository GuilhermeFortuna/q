# Q-078 implementation plan: Launcher respects saved terminal setup

> **For implementation agents:** Read the linked spec and repository instructions.
> Use superpowers:executing-plans when that skill is available. Start only through
> `./work start Q-078 --agent <agent> --worktree` after written-plan approval and
> completed dependencies. Implement this task natively; delegation requires separate authorization.

**Goal:** Let ./dev reopen the terminal’s saved chart target while retaining explicit startup overrides.
**Architecture:** dev remains the only lifecycle entrypoint; q_terminal owns its saved UI state.
**Spec:** [Specification](../specs/Q-078-launcher-respects-saved-terminal-setup-spec.md)
**Status:** written plan awaiting human review.

## Global constraints

- The linked spec defines the interface, defaults and acceptance criteria; do not widen scope.
- Use the existing repository toolchain and canonical checks without resource-slice wrappers.
- Commit focused changes on the task branch. Never push, merge or change protected branches.
- Report unavailable prerequisites with the documented board workflow; do not substitute shortcuts.

## Ordered implementation

- [ ] 1. Extend tools/tests/test-dev with subprocess launch fixtures for unset, empty, explicit and one-field-only target environments; assert the actual environment seen by mocked make.
- [ ] 2. Adjust launch_terminal in dev to stop synthesizing target values, normalize empty overrides to absence and retain API-base export.
- [ ] 3. Exercise all/default, live, legacy and shell dispatch plus already-running pidfile reuse in the mock harness. Confirm no shell command reads q_terminal workspace files.
- [ ] 4. Update README.md target examples and precedence; run bash -n dev and tools/tests/test-dev, commit and report focused results.

## Review focus

- Empty exported values behave like absence; the mocked child environment proves it.
- One explicit field does not force a default for the other; paired precedence cases cover this.
- Already-running terminals are not restarted; the pidfile test asserts no launch call.
- API-base isolation remains valid; the existing live/research mock cases remain in the harness.
- Interactive shell uses the common handler; its mocked transcript exercises terminal launch.

## Validation and handoff

Run `bash -n dev` and `tools/tests/test-dev` from the workspace root. No full CI or live-stack run is required.

Record acceptance results, exact dependency pins, any manual evidence and open follow-ups.
Commit the final changes, then run `./work board set Q-078 in-review -m "<changes; checks and results; follow-ups>"`
from the workspace root. The human owns integration and any required release.
