"""Command-line entry point for ./work."""

from __future__ import annotations

import argparse
import sys

from qwork.agents import AGENTS, DEFAULT_EFFORT
from qwork.board import AGENT_TARGETS
from qwork.context import Context
from qwork.errors import QworkError


def _default_models() -> str:
    defaults = [f"{name} {spec.default_model}" for name, spec in AGENTS.items() if spec.default_model]
    return ", ".join(defaults) if defaults else "agent's own"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="work", description="Launch and finish Q board tasks with AI coding agents.")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="start or resume a task with an agent")
    start.add_argument("task_id", metavar="ID")
    start.add_argument("--agent", required=True, choices=list(AGENTS))
    start.add_argument("--effort", help=f"reasoning effort (default: {DEFAULT_EFFORT})")
    start.add_argument("--model", help=f"model passed to the agent (defaults: {_default_models()})")
    start.add_argument("--worktree", action="store_true", help="work in q/.worktrees instead of the repo checkout")
    start.add_argument("--dry-run", action="store_true", help="check and print the prompt without changing anything")

    finish = sub.add_parser("finish", help="merge a reviewed task into development and mark it Done")
    finish.add_argument("task_id", metavar="ID")
    finish.add_argument("--push", action="store_true", help="push development to origin after merging")
    finish.add_argument(
        "--no-push", action="store_true", help="in a release repo, tag locally without pushing anything"
    )

    board = sub.add_parser("board", help="inspect or update a task on the project board")
    board_sub = board.add_subparsers(dest="board_command", required=True)
    show = board_sub.add_parser("show", help="show a task")
    show.add_argument("task_id", metavar="ID")
    set_ = board_sub.add_parser("set", help="set a task's status (agents)")
    set_.add_argument("task_id", metavar="ID")
    set_.add_argument("target", choices=list(AGENT_TARGETS))
    set_.add_argument("-m", "--message", help="comment posted on the issue")
    return parser


def main(argv: list[str] | None = None, ctx: Context | None = None) -> int:
    args = build_parser().parse_args(argv)
    ctx = ctx or Context.default()
    try:
        if args.command == "start":
            from qwork.start import start

            return start(ctx, args.task_id, args.agent, args.effort, args.model, args.worktree, args.dry_run)
        if args.command == "finish":
            from qwork.finish import finish

            return finish(ctx, args.task_id, args.push, args.no_push)
        from qwork.commands import board_set, board_show

        if args.board_command == "show":
            return board_show(ctx, args.task_id)
        return board_set(ctx, args.task_id, args.target, args.message)
    except QworkError as exc:
        print(f"work: {exc}", file=ctx.err)
        return 1


def entry() -> None:
    sys.exit(main())
