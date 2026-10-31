# Agent models

The models available for work on Q, and what each one is good for. Planning agents read this
file instead of researching models when they suggest who should build a task (see
"Authoring tasks" in [`AGENTS.md`](../AGENTS.md)).

- **You own [Roster](#roster):** add or remove a row whenever your access changes.
- **Agents own [Profiles](#profiles):** after adding rows, run `./work models document`. Run
  `./work models refresh` when you want every profile researched again
  ([commands](work-cli.md#work-models)).

## Roster

`Agent` is the `--agent` value of `./work start`; `Model` is its `--model` value.

| Agent | Model | Notes |
|---|---|---|
| claude | `claude-fable-5-1` | Fable 5.1 |
| claude | `claude-opus-5-5` | Opus 5.5 |
| claude | `claude-sonnet-5-5` | Sonnet 5.5 |
| claude | `claude-haiku-5-5` | Haiku 5.5 |
| codex | `gpt-6.1-sol` |  |
| codex | `gpt-6.1-terra` |  |
| codex | `gpt-6-astra` |  |
| codex | `gpt-6-sol` |  |
| codex | `gpt-6-luna` |  |
| codex | `gpt-5.6-sol` |  |
| codex | `gpt-5.6-terra` |  |
| codex | `gpt-5.6-luna` |  |
| antigravity | `gemini-4-argon-{low,medium,high}` | Gemini 4 Argon; the suffix is part of the `--model` value |
| antigravity | `gemini-3.8-flash-{low,medium,high}` | Gemini 3.8 Flash; the suffix is part of the `--model` value |
| antigravity | `claude-opus-5-5-{low,medium,high}` | Opus 5.5 through Antigravity; the suffix is part of the `--model` value |
| antigravity | `claude-sonnet-5-5-{low,medium,high}` | Sonnet 5.5 through Antigravity; the suffix is part of the `--model` value |
| antigravity | `gpt-oss-120b-medium` | GPT-OSS 120B |

## Difficulty scale

| Level | Typical work |
|---|---|
| `D1 routine` | Documentation, mechanical edits, and small changes that follow an existing pattern |
| `D2 standard` | A feature or fix in one repository with clear behavior and existing patterns |
| `D3 hard` | Cross-repository changes, new abstractions, or subtle debugging |
| `D4 critical` | Order execution, ledger and risk safety; deterministic kernels; concurrency; wire-contract design |

A task's level is set by its hardest essential part and the cost of a mistake, not by its size.

## Profiles

No profiles yet.
