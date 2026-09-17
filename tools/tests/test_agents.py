import pytest

from qwork.agents import AGENTS, build_command
from qwork.errors import QworkError


def test_claude_default_effort():
    launch = build_command("claude", "PROMPT", None, None)
    assert launch.argv == ["claude", "--effort", "medium", "PROMPT"]
    assert launch.notice is None


def test_claude_with_model_and_max_effort():
    assert build_command("claude", "P", "max", "opus").argv == ["claude", "--model", "opus", "--effort", "max", "P"]


def test_codex_effort_through_config():
    assert build_command("codex", "P", "high", "gpt-5").argv == ["codex", "-m", "gpt-5", "-c", "model_reasoning_effort=high", "P"]


def test_codex_defaults_to_terra():
    assert build_command("codex", "P", None, None).argv == [
        "codex",
        "-m",
        "gpt-5.6-terra",
        "-c",
        "model_reasoning_effort=medium",
        "P",
    ]


def test_cursor_effort_is_a_model_parameter():
    assert build_command("cursor", "P", "high", "sonnet-5").argv == ["agent", "--model", "sonnet-5[effort=high]", "P"]


def test_cursor_model_without_effort_is_passed_unparameterized():
    launch = build_command("cursor", "P", None, "composer-2.5")
    assert launch.argv == ["agent", "--model", "composer-2.5", "P"]
    assert "effort not applied" in launch.notice


def test_cursor_without_model_skips_default_effort_with_notice():
    launch = build_command("cursor", "P", None, None)
    assert launch.argv == ["agent", "P"]
    assert "effort not applied" in launch.notice


def test_cursor_explicit_effort_without_model_is_an_error():
    with pytest.raises(QworkError, match="pass --model"):
        build_command("cursor", "P", "high", None)


def test_antigravity_interactive_prompt():
    assert build_command("antigravity", "P", None, "gemini-3-pro").argv == [
        "agy", "--model", "gemini-3-pro", "--effort", "medium", "-i", "P"
    ]


@pytest.mark.parametrize(("agent", "effort"), [("antigravity", "xhigh"), ("codex", "max"), ("claude", "minimal")])
def test_unsupported_effort_is_an_error(agent, effort):
    with pytest.raises(QworkError, match=f"{agent} does not support effort '{effort}'"):
        build_command(agent, "P", effort, None)


def test_executables():
    assert {name: spec.executable for name, spec in AGENTS.items()} == {
        "claude": "claude", "codex": "codex", "cursor": "agent", "antigravity": "agy"
    }
