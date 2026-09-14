"""Render agent prompt templates from tools/prompts."""

from __future__ import annotations

import string
from pathlib import Path

from qwork.errors import QworkError

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def render(name: str, values: dict[str, str], prompts_dir: Path = PROMPTS_DIR) -> str:
    path = prompts_dir / f"{name}.md"
    if not path.is_file():
        raise QworkError(f"prompt template not found: {path}")
    template = string.Template(path.read_text(encoding="utf-8"))
    unused = sorted(set(values) - set(template.get_identifiers()))
    if unused:
        raise QworkError(f"prompt template {path.name} does not use: {', '.join(unused)}")
    try:
        return template.substitute(values)
    except KeyError as exc:
        raise QworkError(f"prompt template {path.name} uses unknown placeholder ${exc.args[0]}") from None
    except ValueError as exc:
        raise QworkError(f"prompt template {path.name} is malformed: {exc}") from None
