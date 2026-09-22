"""Run agents inside the ai-agents cgroup slice, with capped build parallelism.

`./work start` launches an agent with `execvp`, which resolves a binary on PATH
and never sees the shell functions in ~/.local/share/q-slices/shell.sh. An agent
started this way inherits the launching terminal's cgroup -- `desktop.slice`,
the highest-priority slice on the box, with no memory limit -- so it must be
placed in its slice here instead.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

SLICE = "ai-agents"
SLICE_RUN = "slice-run"

# One rustc plus one linker per core is what exhausted the machine's RAM: a
# cgroup memory limit does not help when 32 gold linkers allocate faster than
# reclaim, and the kernel picks a global OOM victim. Cap the fan-out instead.
BUILD_JOBS = 6

BUILD_VARS = ("CARGO_BUILD_JOBS", "MAKEFLAGS", "CMAKE_BUILD_PARALLEL_LEVEL")


def build_env(env: Mapping[str, str], jobs: int = BUILD_JOBS) -> dict[str, str]:
    """`env` with build parallelism capped, leaving any explicit setting alone."""
    capped = dict(env)
    capped.setdefault("CARGO_BUILD_JOBS", str(jobs))
    capped.setdefault("MAKEFLAGS", f"-j{jobs}")
    capped.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", str(jobs))
    return capped


def confine(argv: list[str], which: Callable[[str], str | None]) -> tuple[list[str], str | None]:
    """`argv` wrapped to run inside the ai-agents slice, and a notice if it cannot be."""
    if which(SLICE_RUN) is None:
        return argv, f"{SLICE_RUN} not on PATH; agent runs unconfined, outside {SLICE}.slice"
    return [SLICE_RUN, SLICE, *argv], None
