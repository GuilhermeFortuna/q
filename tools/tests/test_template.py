import pytest

from qwork.errors import QworkError
from qwork.template import render

VALUES = {
    "id": "Q-010",
    "title": "Q-010 — Transactional outbox",
    "repo": "q_backend",
    "issue_url": "https://github.com/GuilhermeFortuna/q_backend/issues/1",
    "spec": "q_backend/docs/development/specs/Q-010-transactional-outbox-spec.md",
    "plan": "q_backend/docs/development/plans/Q-010-transactional-outbox-plan.md",
    "workdir": "q_backend",
    "branch": "Q-010-transactional-outbox",
    "resume": "",
    "repo_agents": "`q_backend/README.md`",
}


def test_implement_template_renders(tmp_path):
    text = render("implement", VALUES)
    assert "Q-010 — Transactional outbox" in text
    assert "q_backend/docs/development/plans/Q-010-transactional-outbox-plan.md" in text
    assert "./work board set Q-010 in-review" in text
    assert "./work board set Q-010 blocked" in text
    assert "$" not in text.replace("$ ", "")


def test_unknown_placeholder_is_an_error(tmp_path):
    (tmp_path / "t.md").write_text("Hello $who")
    with pytest.raises(QworkError, match=r"unknown placeholder \$who"):
        render("t", {}, prompts_dir=tmp_path)


def test_unused_value_is_an_error(tmp_path):
    (tmp_path / "t.md").write_text("Hello $who")
    with pytest.raises(QworkError, match="does not use: extra"):
        render("t", {"who": "x", "extra": "y"}, prompts_dir=tmp_path)


def test_missing_template_is_an_error(tmp_path):
    with pytest.raises(QworkError, match="not found"):
        render("nope", {}, prompts_dir=tmp_path)
