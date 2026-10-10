"""Structured-output clients bound to one provider and model."""

from __future__ import annotations

import re
from typing import Any, Protocol, TypeVar

import instructor
from pydantic import BaseModel

from .env import resolve_key
from .providers import DEFAULT_PROVIDER, _spec

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    def create(self, *, response_model: type[T], messages: Any, max_tokens: int,
               **kwargs: Any) -> T: ...


_SAMPLING_MODELS = re.compile(r"claude-(3|(opus|sonnet|haiku)-4-[0-6](\b|-))")


class AnthropicClient:
    """Structured output through Anthropic's native `messages.parse` (no forced tool use).

    Claude 5.5-generation models reject forced `tool_choice`, `anthropic` 1.x dropped the
    `temperature` keyword, and Claude Opus 4.7+ rejects sampling parameters outright, so this
    path uses JSON-schema structured outputs and only sends `temperature` to models that take it.
    """

    def __init__(self, model: str, api_key: str | None = None) -> None:
        from anthropic import Anthropic

        self.model = model
        self.client = Anthropic(api_key=api_key) if api_key else Anthropic()

    def create(self, *, response_model: type[T], messages: Any, max_tokens: int,
               temperature: float | None = None, **kwargs: Any) -> T:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [m for m in messages if m["role"] != "system"]
        extra: dict[str, Any] = {}
        if temperature is not None and _SAMPLING_MODELS.match(self.model):
            extra["extra_body"] = {"temperature": temperature}
        if system:
            extra["system"] = system
        response = self.client.messages.parse(
            model=self.model, max_tokens=max_tokens, messages=turns,
            output_format=response_model, **extra, **kwargs,
        )
        if response.parsed_output is None:
            raise RuntimeError(
                f"{self.model} returned no structured output (stop_reason="
                f"{response.stop_reason!r}). Try a larger max_tokens or a different model."
            )
        return response.parsed_output


def build_client(
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
    key: str | None = None,
) -> LLMClient:
    """Build a structured-output client for `provider`/`model`, key from arg or env."""
    spec = _spec(provider)
    model = model or spec.default_model
    resolved = resolve_key(provider, key)
    if provider == "anthropic":
        return AnthropicClient(model, resolved)
    target = f"{spec.prefix}/{model}"
    if resolved:
        return instructor.from_provider(target, api_key=resolved)
    return instructor.from_provider(target)
