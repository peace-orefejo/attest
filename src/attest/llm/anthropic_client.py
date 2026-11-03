"""Structured output through Anthropic's native JSON-schema outputs, without forced tool use."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Literal, TypeVar

import instructor
from anthropic import Anthropic, Omit, omit, transform_schema
from anthropic.types import (
    CacheControlEphemeralParam,
    Message,
    MessageParam,
    OutputConfigParam,
    TextBlockParam,
    ThinkingConfigParam,
)
from pydantic import BaseModel

from .anthropic_answer import structured_answer
from .reasoning import Reasoning, answer_room
from .thinking import ClaudePlan, claude_plan

T = TypeVar("T", bound=BaseModel)

_SAMPLING_MODELS = re.compile(
    r"claude-(3|(opus|sonnet|haiku)-4-[0-6](\b|-)|(opus|sonnet|haiku)-4-\d{8}\b)"
)


def accepts_temperature(model: str) -> bool:
    """Claude Opus 4.7+ and the 5.x generation reject sampling parameters outright."""
    return _SAMPLING_MODELS.match(model) is not None


class AnthropicClient:
    """Structured output through Anthropic's native JSON-schema outputs (no forced tool use).

    Claude 5.5-generation models reject forced `tool_choice`, `anthropic` 1.x dropped the
    `temperature` keyword, and Claude Opus 4.7+ rejects sampling parameters outright, so this
    path uses JSON-schema structured outputs and only sends `temperature` to models that take it.
    The answer is validated here rather than by the SDK's `messages.parse`, so a cut-off answer
    raises `TruncatedOutput` carrying the billed message instead of a bare validation error.
    A `reasoning` level becomes `thinking` and `output_config.effort` for the models listed in
    `attest.llm.thinking`, with room for the thinking added to `max_tokens`.
    """

    provider = instructor.Provider.ANTHROPIC
    supports_reasoning = True

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        self.client = Anthropic(api_key=api_key) if api_key else Anthropic()

    def create(
        self,
        *,
        response_model: type[T],
        messages: Sequence[Mapping[str, object]],
        max_tokens: int,
        temperature: float | None = None,
        reasoning: Reasoning | None = None,
    ) -> T:
        result, _ = self.create_with_completion(
            response_model=response_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning=reasoning,
        )
        return result

    def create_with_completion(
        self,
        *,
        response_model: type[T],
        messages: Sequence[Mapping[str, object]],
        max_tokens: int,
        temperature: float | None = None,
        reasoning: Reasoning | None = None,
    ) -> tuple[T, Message]:
        system = system_text(messages)
        plan = claude_plan(self.model, reasoning) if reasoning is not None else None
        response = self.client.messages.create(
            model=self.model,
            max_tokens=answer_room(max_tokens, plan.room) if plan else max_tokens,
            messages=conversation_turns(messages),
            system=system or omit,
            thinking=_thinking(plan),
            output_config=_output_config(response_model, plan),
            extra_body=self._body(temperature, plan),
        )
        return structured_answer(response, response_model, self.model), response

    def _body(self, temperature: float | None, plan: ClaudePlan | None) -> dict[str, object] | None:
        body: dict[str, object] = {}
        if temperature is not None and accepts_temperature(self.model):
            body["temperature"] = temperature
        if plan is not None and plan.thinking == "between_tools":
            body["thinking"] = {"type": "between_tools"}
        return body or None


def _thinking(plan: ClaudePlan | None) -> ThinkingConfigParam | Omit:
    if plan is None or plan.thinking is None or plan.thinking == "between_tools":
        return omit
    if plan.thinking == "disabled":
        return {"type": "disabled"}
    return {"type": "adaptive"}


def _output_config(output: type[BaseModel], plan: ClaudePlan | None) -> OutputConfigParam:
    config: OutputConfigParam = {
        "format": {"type": "json_schema", "schema": transform_schema(output.model_json_schema())}
    }
    if plan is not None:
        config["effort"] = plan.effort
    return config


class _TextPart(BaseModel):
    type: Literal["text"]
    text: str
    cache_control: dict[str, str] | None = None


class _Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str | list[_TextPart]


def system_text(messages: Sequence[Mapping[str, object]]) -> str:
    parsed = [_Message.model_validate(m) for m in messages]
    return "\n\n".join(_plain(m.content) for m in parsed if m.role == "system")


def conversation_turns(messages: Sequence[Mapping[str, object]]) -> list[MessageParam]:
    turns: list[MessageParam] = []
    for message in (_Message.model_validate(m) for m in messages):
        if message.role == "system":
            continue
        content = message.content
        if isinstance(content, str):
            turns.append({"role": message.role, "content": content})
        else:
            turns.append({"role": message.role, "content": [_block(p) for p in content]})
    return turns


def _plain(content: str | list[_TextPart]) -> str:
    return content if isinstance(content, str) else "\n\n".join(p.text for p in content)


def _block(part: _TextPart) -> TextBlockParam:
    block: TextBlockParam = {"type": "text", "text": part.text}
    if part.cache_control is not None:
        block["cache_control"] = _EPHEMERAL
    return block


_EPHEMERAL: CacheControlEphemeralParam = {"type": "ephemeral"}
