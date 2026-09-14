"""Supported agent CLIs and how to launch them."""

from __future__ import annotations

from dataclasses import dataclass

from qwork.errors import QworkError

DEFAULT_EFFORT = "medium"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    executable: str
    efforts: tuple[str, ...]


AGENTS = {
    "claude": AgentSpec("claude", "claude", ("low", "medium", "high", "xhigh", "max")),
    "codex": AgentSpec("codex", "codex", ("minimal", "low", "medium", "high", "xhigh")),
    "cursor": AgentSpec("cursor", "agent", ("low", "medium", "high", "xhigh", "max")),
    "antigravity": AgentSpec("antigravity", "agy", ("low", "medium", "high")),
}


@dataclass(frozen=True)
class Launch:
    argv: list[str]
    notice: str | None = None


def build_command(agent: str, prompt: str, effort: str | None, model: str | None) -> Launch:
    spec = AGENTS[agent]
    explicit = effort is not None
    effort = effort or DEFAULT_EFFORT
    if effort not in spec.efforts:
        raise QworkError(f"{agent} does not support effort '{effort}' (allowed: {', '.join(spec.efforts)})")

    if agent == "claude":
        model_args = ["--model", model] if model else []
        return Launch(["claude", *model_args, "--effort", effort, prompt])
    if agent == "codex":
        model_args = ["-m", model] if model else []
        return Launch(["codex", *model_args, "-c", f"model_reasoning_effort={effort}", prompt])
    if agent == "cursor":
        if model:
            return Launch(["agent", "--model", f"{model}[effort={effort}]", prompt])
        if explicit:
            raise QworkError("cursor applies effort through the model; pass --model with --effort")
        return Launch(["agent", prompt], notice="cursor: default effort not applied (no --model given)")
    model_args = ["--model", model] if model else []
    return Launch(["agy", *model_args, "--effort", effort, "-i", prompt])
