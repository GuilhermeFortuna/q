# Batch 13 — Persistent terminal setup and live market analysis

**Status:** written task specs and plans await human review. The [project board](https://github.com/users/GuilhermeFortuna/projects/2) is the status of record.

## Outcome

Open q_terminal with the previous symbol, timeframe, studies, layout and settings already restored, at live prices. Inspect current-session tape, volume delta, cumulative delta, trade rate and large prints. Read separate, explainable trend/momentum/volatility/VWAP context with adjustable settings and confirmed changes.

## Tasks

| Task | Repository | Depends on | Issue |
| --- | --- | --- | --- |
| Q-077 — Automatic terminal setup persistence | q_terminal | Q-076 | Publication pending |
| Q-078 — Launcher respects saved terminal setup | q | Q-077 | Publication pending |
| Q-079 — Trade stream and session history contracts | q_contracts | Q-009 | Publication pending |
| Q-080 — Session trade ingestion and replay | q_backend | Q-079 | Publication pending |
| Q-081 — Deterministic volume analysis kernels | q_core | Q-074, Q-079 | Publication pending |
| Q-082 — Tape panel and volume studies | q_terminal | Q-077, Q-080, Q-081 | Publication pending |
| Q-083 — Explainable market context kernels | q_core | Q-074 | Publication pending |
| Q-084 — Live context, evidence and confirmed changes | q_terminal | Q-077, Q-082, Q-083 | Publication pending |

## Delivery order

1. Persistence: Q-077, then Q-078.
2. Tape foundation: Q-079, Q-080 and Q-081; then Q-082.
3. Market context: Q-083, then Q-084. Q-083 can be developed independently after Q-074; the terminal ultimately pins a release containing both new kernel tasks.

## Decisions

- One active chart; built-in Q indicators with configurable parameters. No formula editor, multiple-timeframe feeds or model-generated commentary.
- Automatic save with a 500 ms debounce and atomic replacement; restore the last workspace at live prices with saved zoom. Explicit startup overrides are session-only until an operator target edit.
- Full current exchange-local day tape backfill joins a non-coalescing trade stream at a publisher-owned frozen watermark. History/transport completeness and aggressor classification are separate statuses.
- Only explicit BUY/SELL flags classify aggressors. Unknown volume remains visible; equal-looking prints retain source multiplicity. Quote-only updates are not trades.
- Volume tools: bar delta, session cumulative delta, trailing 10-second trade rate and large prints at a default threshold of 100 source units. Threshold/window settings and tape filters persist.
- Compact tape list: latest 1000 rows, display filters independent of analytics. Full-session calculation history uses bounded columnar temporary storage.
- Independent context defaults: EMA 9/21, RSI 14 with 30/70, ATR 14 against SMA 20 and 0.8/1.2 ratios, VWAP extension at 1 ATR. Separate evidence, provisional forming-bar readings and confirmed completed-bar changes.
- Latest 100 confirmed context changes remain in memory. Replay, rebuild and settings edits do not create historical event bursts.

## Specification and plan files

Each task has exactly one specification under docs/development/specs and one plan under docs/development/plans in its owning repository:

- **q_terminal / Q-077**: `docs/development/specs/Q-077-automatic-terminal-setup-persistence-spec.md` and `docs/development/plans/Q-077-automatic-terminal-setup-persistence-plan.md`.
- **q / Q-078**: `docs/development/specs/Q-078-launcher-respects-saved-terminal-setup-spec.md` and `docs/development/plans/Q-078-launcher-respects-saved-terminal-setup-plan.md`.
- **q_contracts / Q-079**: `docs/development/specs/Q-079-trade-stream-and-session-history-contracts-spec.md` and `docs/development/plans/Q-079-trade-stream-and-session-history-contracts-plan.md`.
- **q_backend / Q-080**: `docs/development/specs/Q-080-session-trade-ingestion-and-replay-spec.md` and `docs/development/plans/Q-080-session-trade-ingestion-and-replay-plan.md`.
- **q_core / Q-081**: `docs/development/specs/Q-081-deterministic-volume-analysis-kernels-spec.md` and `docs/development/plans/Q-081-deterministic-volume-analysis-kernels-plan.md`.
- **q_terminal / Q-082**: `docs/development/specs/Q-082-tape-panel-and-volume-studies-spec.md` and `docs/development/plans/Q-082-tape-panel-and-volume-studies-plan.md`.
- **q_core / Q-083**: `docs/development/specs/Q-083-explainable-market-context-kernels-spec.md` and `docs/development/plans/Q-083-explainable-market-context-kernels-plan.md`.
- **q_terminal / Q-084**: `docs/development/specs/Q-084-live-context-evidence-and-confirmed-changes-spec.md` and `docs/development/plans/Q-084-live-context-evidence-and-confirmed-changes-plan.md`.

## Review and integration

Documentation is committed on local docs/batch-13-live-analysis branches in isolated worktrees under .worktrees/<repository>/docs-batch-13-live-analysis. No branch is pushed or merged by the authoring session. Complete spec/plan text is embedded in each issue so remote review is possible before publication.

The human integrates/publishes these documentation branches before launching implementation tasks. Agents never promote a task to Todo. The authoring session adds issues and Batch/Depends on metadata but does not initialize or change Status. The current work CLI only changes agent statuses from In Progress, so initial approval status is human-owned.

Launch an approved task with completed dependencies from the workspace root using ./work start Q-NNN --agent <agent> --worktree. Follow the task plan’s focused tests and canonical gates; normal human ./work finish performs integration and q_core release.

## Acceptance milestone

Reopen without configuring the terminal again; obtain a complete current-session tape after history/live joining; change volume/context settings and inspect their evidence; recover a simulated gap without double-counting trades or producing false context events. Fake-source tests establish correctness, gallery review establishes presentation, and the combined frame benchmark keeps p95 below 16 ms. No live orders are part of acceptance.
