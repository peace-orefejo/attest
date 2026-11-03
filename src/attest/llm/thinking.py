"""Per-model reasoning controls: which models take a reasoning setting, and what each level sends.

This is the one table of model capabilities. A model not listed here (an older or unknown one)
gets no reasoning parameter and no extra `max_tokens`, exactly as before.

Anthropic, Claude 5.5 (`thinking` and `output_config.effort`):

- Haiku 5.5: adaptive thinking is on by default; `{"type": "disabled"}` turns it off (only at
  effort high or below). Default effort is medium.
- Sonnet 5.5: `{"type": "disabled"}` is rejected; `{"type": "between_tools"}` turns thinking off
  (only at effort high or below). That type isn't in the SDK's types yet, so it is sent in the
  request body. Default effort is high.
- Opus 5.5: thinking can't be turned off, so effort is the only control; default medium.
- `budget_tokens` is rejected by all three, so it is never sent. Thinking tokens are billed as
  output and count against `max_tokens`.

OpenAI (`reasoning_effort`): there is no adaptive mode, so "auto" uses "low", the lowest effort
that still reasons; "off" sends "none". OpenAI reasoning models only take `temperature` when
reasoning is off, so it is left out otherwise.

Gemini (`thinking_config`): "auto" is dynamic thinking (`thinking_budget=-1`); the other levels
set `thinking_level`, and "off" uses the model's lowest level.

Every model gets one fixed level per call site within a run, so a cached prompt prefix is
never invalidated by an effort change between calls.
"""

from __future__ import annotations

from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict

from .reasoning import Reasoning

Effort = Literal["low", "medium", "high"]
ClaudeOff = Literal["disabled", "between_tools", "never"]
OpenAIEffort = Literal["none", "low", "medium", "high"]
GeminiLevel = Literal["MINIMAL", "LOW", "MEDIUM", "HIGH"]
V = TypeVar("V")

CLAUDE_MODELS: dict[str, ClaudeOff] = {
    "claude-haiku-5-5": "disabled",
    "claude-sonnet-5-5": "between_tools",
    "claude-opus-5-5": "never",
}
"""Claude models that take adaptive thinking and effort, with how each turns thinking off."""

OPENAI_MODELS: frozenset[str] = frozenset(
    {"gpt-6-astra", "gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna"}
)
"""OpenAI models that take `reasoning_effort`, including `"none"`."""

GEMINI_MODELS: dict[str, GeminiLevel] = {
    "gemini-4-argon": "LOW",
    "gemini-3.8-flash": "MINIMAL",
    "gemini-3.5-flash-lite": "MINIMAL",
}
"""Gemini models that take `thinking_config`, with the lowest `thinking_level` each accepts."""

_EFFORT: dict[Reasoning, Effort] = {
    "auto": "low",
    "off": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
}


class Plan(BaseModel):
    """What one call sends for its reasoning level. `room` is the level whose allowance it gets."""

    model_config = ConfigDict(frozen=True)

    room: Reasoning


class ClaudePlan(Plan):
    thinking: Literal["adaptive", "disabled", "between_tools"] | None = None
    effort: Effort


class OpenAIPlan(Plan):
    effort: OpenAIEffort

    @property
    def takes_temperature(self) -> bool:
        return self.effort == "none"


class GeminiPlan(Plan):
    budget: int | None = None
    level: GeminiLevel | None = None

    def config(self) -> dict[str, int | str]:
        if self.budget is not None:
            return {"thinking_budget": self.budget}
        return {"thinking_level": self.level or "LOW"}


def claude_plan(model: str, level: Reasoning) -> ClaudePlan | None:
    off = _lookup(model, CLAUDE_MODELS)
    if off is None:
        return None
    effort = _EFFORT[level]
    if off == "never":
        return ClaudePlan(effort=effort, room="low" if level == "off" else level)
    if level == "off":
        return ClaudePlan(thinking=off, effort=effort, room="off")
    return ClaudePlan(thinking="adaptive", effort=effort, room=level)


def openai_plan(model: str, level: Reasoning) -> OpenAIPlan | None:
    if _lookup(model, dict.fromkeys(OPENAI_MODELS, True)) is None:
        return None
    if level == "off":
        return OpenAIPlan(effort="none", room="off")
    return OpenAIPlan(effort=_EFFORT[level], room=level)


def gemini_plan(model: str, level: Reasoning) -> GeminiPlan | None:
    lowest = _lookup(model, GEMINI_MODELS)
    if lowest is None:
        return None
    if level == "auto":
        return GeminiPlan(budget=-1, room="auto")
    if level == "off":
        return GeminiPlan(level=lowest, room="low")
    named: dict[Effort, GeminiLevel] = {"low": "LOW", "medium": "MEDIUM", "high": "HIGH"}
    return GeminiPlan(level=named[_EFFORT[level]], room=level)


def model_takes_reasoning(provider: str, model: str) -> bool:
    """Whether attest sends `model` a reasoning setting: it is listed here for `provider`."""
    if provider == "anthropic":
        return claude_plan(model, "auto") is not None
    if provider == "openai":
        return openai_plan(model, "auto") is not None
    if provider == "gemini":
        return gemini_plan(model, "auto") is not None
    return False


def _lookup(model: str, table: dict[str, V]) -> V | None:
    """The row for `model`, matching an exact id or one with a version suffix (`-20260101`)."""
    name = model.removeprefix("models/")
    for known, row in table.items():
        if name == known or name.startswith((f"{known}-", f"{known}@", f"{known}[")):
            return row
    return None
