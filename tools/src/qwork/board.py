"""Read and update tasks on the Q GitHub Project board through the gh CLI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cached_property

from qwork.errors import QworkError
from qwork.runner import Runner, run

OWNER = "GuilhermeFortuna"
PROJECT_NUMBER = 2

BLOCKED = "Blocked"
TODO = "Todo"
IN_PROGRESS = "In Progress"
IN_REVIEW = "In Review"
DONE = "Done"

TASK_ID_RE = re.compile(r"^Q-\d{3}$")
TASK_ID_IN_TEXT_RE = re.compile(r"Q-\d{3}")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def validate_task_id(task_id: str) -> str:
    if not TASK_ID_RE.match(task_id):
        raise QworkError(f"invalid task ID '{task_id}' (expected Q-NNN)")
    return task_id


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    status: str
    repo_full: str
    issue_number: int
    issue_url: str
    depends_on: tuple[str, ...]
    item_id: str

    @property
    def repo(self) -> str:
        return self.repo_full.split("/", 1)[1]

    @property
    def branch(self) -> str:
        name = re.sub(rf"^{re.escape(self.id)}\s*[—–-]?\s*", "", self.title)
        return f"{self.id}-{slugify(name)}"


def parse_task(item: dict) -> Task:
    content = item.get("content") or {}
    title = item.get("title", "")
    if content.get("type") != "Issue":
        raise QworkError(f"board item '{title}' is not an issue")
    return Task(
        id=title.split()[0],
        title=title,
        status=item.get("status") or "",
        repo_full=content["repository"],
        issue_number=int(content["number"]),
        issue_url=content["url"],
        depends_on=tuple(TASK_ID_IN_TEXT_RE.findall(item.get("depends on") or "")),
        item_id=item["id"],
    )


class Board:
    def __init__(self, runner: Runner = run) -> None:
        self._run = runner

    def _project_json(self, *args: str) -> dict:
        return json.loads(self._run(["gh", "project", *args, "--owner", OWNER, "--format", "json"]))

    @cached_property
    def _items(self) -> list[dict]:
        return self._project_json("item-list", str(PROJECT_NUMBER), "--limit", "500")["items"]

    def task(self, task_id: str) -> Task:
        validate_task_id(task_id)
        matches = [i for i in self._items if i.get("title", "").startswith(f"{task_id} ")]
        if not matches:
            raise QworkError(f"{task_id} is not on the board")
        if len(matches) > 1:
            raise QworkError(f"{task_id} matches {len(matches)} board items")
        return parse_task(matches[0])
