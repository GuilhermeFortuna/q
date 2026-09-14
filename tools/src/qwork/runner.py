"""The single place qwork runs external commands (gh, git)."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from qwork.errors import QworkError


class CommandError(QworkError):
    def __init__(self, command: Sequence[str], returncode: int, stderr: str) -> None:
        self.command = list(command)
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"`{' '.join(self.command)}` failed ({returncode}): {stderr.strip()}")


class Runner(Protocol):
    def __call__(self, args: Sequence[str], cwd: Path | None = None) -> str: ...


def run(args: Sequence[str], cwd: Path | None = None) -> str:
    try:
        proc = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise QworkError(f"'{args[0]}' is not installed or not on PATH") from None
    if proc.returncode != 0:
        raise CommandError(args, proc.returncode, proc.stderr)
    return proc.stdout
