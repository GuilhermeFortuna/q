import pytest

from helpers import FakeRunner, item
from qwork.board import Board, check_agent_transition
from qwork.errors import QworkError


def make(status="In Progress", **kwargs):
    fake = FakeRunner([item("Q-010", "Transactional outbox", status)], **kwargs)
    board = Board(fake)
    return fake, board, board.task("Q-010")


def test_set_status_edits_the_item_with_resolved_ids():
    fake, board, task = make()
    board.set_status(task, "In Review")
    [edit] = fake.gh("gh", "project", "item-edit")
    assert edit[edit.index("--project-id") + 1] == "PVT_test"
    assert edit[edit.index("--field-id") + 1] == "F_status"
    assert fake.status_edits() == [("PVTI_Q-010", "In Review")]


def test_set_status_without_board_option_is_an_error():
    fake, board, task = make(status_options=("Blocked", "Todo", "In Progress", "Done"))
    with pytest.raises(QworkError, match="no 'In Review' option"):
        board.set_status(task, "In Review")
    assert fake.gh("gh", "project", "item-edit") == []


def test_field_ids_are_resolved_once():
    fake, board, task = make()
    board.set_status(task, "In Review")
    board.set_status(task, "Done")
    assert len(fake.gh("gh", "project", "view")) == 1
    assert len(fake.gh("gh", "project", "field-list")) == 1


def test_comment_and_close_target_the_issue():
    fake, board, task = make()
    board.comment(task, "hello")
    board.close(task, "merged")
    assert fake.gh("gh", "issue", "comment") == [
        ["gh", "issue", "comment", "1", "--repo", "GuilhermeFortuna/q_backend", "--body", "hello"]
    ]
    assert fake.gh("gh", "issue", "close") == [
        ["gh", "issue", "close", "1", "--repo", "GuilhermeFortuna/q_backend", "--comment", "merged"]
    ]


def test_agent_can_move_in_progress_to_in_review():
    _, _, task = make()
    assert check_agent_transition(task, "in-review", None) == "In Review"


def test_agent_can_block_with_a_reason():
    _, _, task = make()
    assert check_agent_transition(task, "blocked", "needs Q-009 schema") == "Blocked"


def test_blocked_requires_a_reason():
    _, _, task = make()
    with pytest.raises(QworkError, match="requires -m"):
        check_agent_transition(task, "blocked", None)


@pytest.mark.parametrize("status", ["Todo", "Blocked", "In Review", "Done"])
def test_agent_transitions_only_from_in_progress(status):
    _, _, task = make(status=status)
    with pytest.raises(QworkError, match="only from 'In Progress'"):
        check_agent_transition(task, "in-review", "x")


@pytest.mark.parametrize("target", ["done", "todo", "in-progress"])
def test_agent_cannot_choose_other_targets(target):
    _, _, task = make()
    with pytest.raises(QworkError, match="agents may only set"):
        check_agent_transition(task, target, "x")
