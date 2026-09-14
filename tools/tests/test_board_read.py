import pytest

from helpers import FakeRunner, item
from qwork.board import Board, slugify
from qwork.errors import QworkError


def test_task_is_parsed_from_board_item():
    board = Board(FakeRunner([item("Q-011", "Redis Streams relay and ephemeral publisher", "Todo", number=2, depends="Q-010")]))
    task = board.task("Q-011")
    assert task.id == "Q-011"
    assert task.status == "Todo"
    assert task.repo_full == "GuilhermeFortuna/q_backend"
    assert task.repo == "q_backend"
    assert task.issue_number == 2
    assert task.issue_url == "https://github.com/GuilhermeFortuna/q_backend/issues/2"
    assert task.depends_on == ("Q-010",)
    assert task.item_id == "PVTI_Q-011"
    assert task.branch == "Q-011-redis-streams-relay-and-ephemeral-publisher"


def test_depends_on_accepts_several_ids_and_blank():
    board = Board(FakeRunner([item("Q-012", "A", "Todo", depends="Q-009, Q-010 Q-011"), item("Q-013", "B", "Todo")]))
    assert board.task("Q-012").depends_on == ("Q-009", "Q-010", "Q-011")
    assert board.task("Q-013").depends_on == ()


@pytest.mark.parametrize(
    ("text", "slug"),
    [
        ("Transactional outbox", "transactional-outbox"),
        ("Job events (on) the stream!", "job-events-on-the-stream"),
        ("  Tauri shell stops owning backend processes ", "tauri-shell-stops-owning-backend-processes"),
    ],
)
def test_slugify(text, slug):
    assert slugify(text) == slug


def test_unknown_task_is_an_error():
    with pytest.raises(QworkError, match="Q-099 is not on the board"):
        Board(FakeRunner([item("Q-010", "A", "Todo")])).task("Q-099")


def test_duplicate_task_is_an_error():
    with pytest.raises(QworkError, match="matches 2 board items"):
        Board(FakeRunner([item("Q-010", "A", "Todo"), item("Q-010", "B", "Todo")])).task("Q-010")


def test_invalid_task_id_is_an_error():
    with pytest.raises(QworkError, match="invalid task ID"):
        Board(FakeRunner([])).task("Q-10")


def test_prefix_must_be_the_whole_id():
    with pytest.raises(QworkError, match="Q-001 is not on the board"):
        Board(FakeRunner([item("Q-0011", "A", "Todo")])).task("Q-001")


def test_draft_items_are_rejected():
    draft = item("Q-010", "A", "Todo")
    draft["content"] = {"type": "DraftIssue", "title": draft["title"]}
    with pytest.raises(QworkError, match="is not an issue"):
        Board(FakeRunner([draft])).task("Q-010")


def test_board_items_are_listed_once():
    fake = FakeRunner([item("Q-010", "A", "Todo"), item("Q-011", "B", "Todo")])
    board = Board(fake)
    board.task("Q-010")
    board.task("Q-011")
    assert len(fake.gh("gh", "project", "item-list")) == 1
