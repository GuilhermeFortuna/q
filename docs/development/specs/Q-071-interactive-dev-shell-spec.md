# Q-071 — Interactive dev shell — spec

**Status:** Awaiting plan approval
**Owner:** `q/` workspace repository
**Depends on:** Q-070

## Goal

Provide an interactive prompt over the Q-070 `./dev` commands for operators who want to manage either stack or both during one session. The noninteractive CLI remains the source of behavior and works without the shell.

## Behavior

`./dev shell` opens a `dev>` prompt and starts no stack. It accepts `up live`, `up research`, `up all`, `down live`, `down research`, `down all`, `status`, `logs <service>`, `restart <service>`, `help`, and `exit`/`quit`. `up` and `down` use the same defaults and validation as their `./dev` counterparts; `up research --host|--container [--rebuild]` forwards mode options. The shell invokes the same command handler as the normal CLI, without a second service implementation. It remains usable after an individual command fails and reports that command's error and exit status.

The prompt is an operator interface, not a Unix shell: it does not evaluate pipelines, redirections, substitutions or arbitrary commands. `logs` follows until Ctrl+C, then returns to the prompt without stopping the service. Ctrl+C at an idle prompt and `exit`/`quit` leave running stacks untouched. EOF exits cleanly. A startup command returns to the prompt after services and UIs launch, so both stacks can be controlled in one session.

## Acceptance

A mocked, noninteractive stdin transcript covers startup, status, selective stop, one failed command followed by a successful command, Ctrl+C/EOF behavior and `exit` without teardown. No real GPU, Wine, Docker containers or desktop apps are required.

**Out of scope:** full-screen terminal UI, command history/completion dependencies, a second lifecycle engine, and changes to backend services.
