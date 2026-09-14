"""Shared test helpers: canned board items and a fake gh runner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from qwork.runner import run

STATUS_OPTIONS = ("Blocked", "Todo", "In Progress", "In Review", "Done")


def item(task_id, title, status, *, repo="q_backend", number=1, depends=None) -> dict:
    full = f"GuilhermeFortuna/{repo}"
    data = {
        "id": f"PVTI_{task_id}",
        "title": f"{task_id} — {title}",
        "status": status,
        "repository": f"https://github.com/{full}",
        "content": {
            "type": "Issue",
            "number": number,
            "repository": full,
            "title": f"{task_id} — {title}",
            "url": f"https://github.com/{full}/issues/{number}",
        },
    }
    if depends is not None:
        data["depends on"] = depends
    return data


class FakeRunner:
    """Answers gh commands from canned board data and runs git for real."""

    def __init__(self, items, status_options=STATUS_OPTIONS):
        self.items = list(items)
        self.status_options = status_options
        self.calls: list[list[str]] = []

    def __call__(self, args, cwd=None):
        args = [str(a) for a in args]
        if args[0] == "git":
            return run(args, cwd)
        self.calls.append(args)
        head = args[:3]
        if head == ["gh", "project", "item-list"]:
            return json.dumps({"items": self.items, "totalCount": len(self.items)})
        if head == ["gh", "project", "view"]:
            return json.dumps({"id": "PVT_test", "number": 2})
        if head == ["gh", "project", "field-list"]:
            options = [{"id": f"opt-{name}", "name": name} for name in self.status_options]
            return json.dumps(
                {
                    "fields": [
                        {"id": "F_title", "name": "Title", "type": "ProjectV2Field"},
                        {
                            "id": "F_status",
                            "name": "Status",
                            "type": "ProjectV2SingleSelectField",
                            "options": options,
                        },
                    ]
                }
            )
        if head in (["gh", "project", "item-edit"], ["gh", "issue", "comment"], ["gh", "issue", "close"]):
            return ""
        raise AssertionError(f"unexpected command: {args}")

    def gh(self, *prefix: str) -> list[list[str]]:
        return [c for c in self.calls if c[: len(prefix)] == list(prefix)]

    def status_edits(self) -> list[tuple[str, str]]:
        return [
            (c[c.index("--id") + 1], c[c.index("--single-select-option-id") + 1].removeprefix("opt-"))
            for c in self.gh("gh", "project", "item-edit")
        ]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
