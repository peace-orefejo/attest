"""Structured output through Anthropic's native `messages.parse`, without forced tool use."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Literal, TypeVar

import instructor
from anthropic import Anthropic, omit
from anthropic.types import CacheControlEphemeralParam, MessageParam, TextBlockParam
from anthropic.types.parsed_message import ParsedMessage
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_SAMPLING_MODELS = re.compile(
    r"claude-(3|(opus|sonnet|haiku)-4-[0-6](\b|-)|(opus|sonnet|haiku)-4-\d{8}\b)"
)


def accepts_temperature(model: str) -> bool:
    """Claude Opus 4.7+ and the 5.x generation reject sampling parameters outright."""
    return _SAMPLING_MODELS.match(model) is not None


class AnthropicClient:
    """Structured output through Anthropic's native `messages.parse` (no forced tool use).

    Claude 5.5-generation models reject forced `tool_choice`, `anthropic` 1.x dropped the
    `temperature` keyword, and Claude Opus 4.7+ rejects sampling parameters outright, so this
    path uses JSON-schema structured outputs and only sends `temperature` to models that take it.
    """

    provider = instructor.Provider.ANTHROPIC

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
    ) -> T:
        result, _ = self.create_with_completion(
            response_model=response_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return result

    def create_with_completion(
        self,
        *,
        response_model: type[T],
        messages: Sequence[Mapping[str, object]],
        max_tokens: int,
        temperature: float | None = None,
    ) -> tuple[T, ParsedMessage[T]]:
        system = system_text(messages)
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=max_tokens,
            messages=conversation_turns(messages),
            output_format=response_model,
            system=system or omit,
            extra_body=self._sampling(temperature),
        )
        if response.parsed_output is None:
            raise RuntimeError(
                f"{self.model} returned no structured output (stop_reason="
                f"{response.stop_reason!r}). Try a larger max_tokens or a different model."
            )
        return response.parsed_output, response

    def _sampling(self, temperature: float | None) -> dict[str, object] | None:
        if temperature is None or not accepts_temperature(self.model):
            return None
        return {"temperature": temperature}


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
