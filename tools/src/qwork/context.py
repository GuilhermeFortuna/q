"""Everything a command needs from the outside world, injectable for tests."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from qwork.board import Board
from qwork.runner import Runner, run, stream


def default_workspace() -> Path:
    env = os.environ.get("QWORK_WORKSPACE")
    return Path(env).resolve() if env else Path(__file__).resolve().parents[3]


@dataclass
class Context:
    workspace: Path
    board: Board
    run: Runner
    stream: Runner
    out: TextIO
    err: TextIO
    execvp: Callable[[str, list[str], dict[str, str]], object]
    which: Callable[[str], str | None]

    @classmethod
    def default(cls) -> Context:
        return cls(
            workspace=default_workspace(),
            board=Board(run),
            run=run,
            stream=stream,
            out=sys.stdout,
            err=sys.stderr,
            execvp=os.execvpe,
            which=shutil.which,
        )
