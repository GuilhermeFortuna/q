"""`work models`: launch an agent to research the profiles in docs/models.md."""

from __future__ import annotations

import os
import shlex

from qwork.agents import build_command
from qwork.confine import build_env, confine
from qwork.context import Context
from qwork.errors import QworkError
from qwork.start import launch_env
from qwork.template import render

MODELS_FILE = "docs/models.md"

SCOPES = {
    "document": (
        "Profile only the roster models that have no section under `## Profiles` yet, and leave "
        "existing profiles alone. If every roster model already has a profile, say so and stop."
    ),
    "refresh": (
        "Research every roster model again and rewrite its profile from what you find now. Delete "
        "profiles of models that are no longer in the roster. Re-rate the whole roster together "
        "so that the ratings stay comparable."
    ),
}


def models(ctx: Context, action: str, agent: str, effort: str | None, model: str | None, dry_run: bool) -> int:
    models_file = ctx.workspace / MODELS_FILE
    if not models_file.is_file():
        raise QworkError(f"{MODELS_FILE} not found in {ctx.workspace}")

    prompt = render(
        "models",
        {"models_file": MODELS_FILE, "scope": SCOPES[action], "workspace": str(ctx.workspace)},
    )
    launch = build_command(agent, prompt, effort, model)
    if launch.notice:
        print(f"work: {launch.notice}", file=ctx.err)
    argv, confine_notice = confine(launch.argv, ctx.which)
    if confine_notice:
        print(f"work: warning: {confine_notice}", file=ctx.err)

    if dry_run:
        print("Dry run — no changes made. Would:", file=ctx.out)
        print(f"  - launch: {shlex.join(argv[:-1])} <prompt>", file=ctx.out)
        print(f"\n--- prompt ---\n{prompt}", file=ctx.out)
        return 0

    print(f"work: models {action}; launching {agent}", file=ctx.err)
    os.chdir(ctx.workspace)
    try:
        ctx.execvp(argv[0], argv, build_env(launch_env(os.environ)))
    except OSError as exc:
        raise QworkError(f"failed to launch '{agent}': {exc}") from None
    return 0
