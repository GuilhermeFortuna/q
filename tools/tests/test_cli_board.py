from helpers import item
from qwork.cli import main


def test_board_show_prints_task(make_ctx):
    ctx, _ = make_ctx([
        item("Q-010", "Transactional outbox", "Todo", depends="Q-009"),
        item("Q-009", "Stream payload", "Done", repo="q_contracts"),
    ])
    assert main(["board", "show", "Q-010"], ctx) == 0
    out = ctx.out.getvalue()
    assert "Q-010  Todo" in out
    assert "depends:  Q-009 (Done)" in out
    assert "spec:     q_backend/docs/development/specs/Q-010-transactional-outbox-spec.md" in out
    assert "branch:   Q-010-transactional-outbox (not created)" in out
    assert "worktree: none" in out


def test_board_set_in_review_updates_status_and_comments(make_ctx):
    ctx, fake = make_ctx([item("Q-010", "Transactional outbox", "In Progress")])
    assert main(["board", "set", "Q-010", "in-review", "-m", "done; tests pass"], ctx) == 0
    assert fake.status_edits() == [("PVTI_Q-010", "In Review")]
    assert fake.gh("gh", "issue", "comment")[0][-1] == "done; tests pass"
    assert "Q-010: In Progress -> In Review" in ctx.out.getvalue()


def test_board_set_blocked_without_message_fails(make_ctx):
    ctx, fake = make_ctx([item("Q-010", "Transactional outbox", "In Progress")])
    assert main(["board", "set", "Q-010", "blocked"], ctx) == 1
    assert "work: blocked requires -m" in ctx.err.getvalue()
    assert fake.status_edits() == []


def test_board_set_from_todo_fails_without_changes(make_ctx):
    ctx, fake = make_ctx([item("Q-010", "Transactional outbox", "Todo")])
    assert main(["board", "set", "Q-010", "in-review", "-m", "x"], ctx) == 1
    assert fake.status_edits() == []
    assert fake.gh("gh", "issue", "comment") == []


def test_board_set_missing_in_review_option_fails_before_comment(make_ctx):
    ctx, fake = make_ctx(
        [item("Q-010", "Transactional outbox", "In Progress")],
        status_options=("Blocked", "Todo", "In Progress", "Done"),
    )
    assert main(["board", "set", "Q-010", "in-review", "-m", "x"], ctx) == 1
    assert "no 'In Review' option" in ctx.err.getvalue()
    assert fake.gh("gh", "issue", "comment") == []
