"""An instructor client (OpenAI, Gemini) that knows its model, so it can send a reasoning level."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from instructor import Instructor
from pydantic import BaseModel

from .reasoning import Reasoning, answer_room
from .thinking import gemini_plan, openai_plan

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam

T = TypeVar("T", bound=BaseModel)


class InstructorClient:
    """Wraps an instructor client built by `attest.providers.build_client`.

    A `reasoning` level becomes `reasoning_effort` (OpenAI) or `thinking_config` (Gemini) for
    the models listed in `attest.llm.thinking`, with room for the reasoning added to
    `max_tokens`. Any other model is called exactly as before.
    """

    supports_reasoning = True

    def __init__(self, inner: Instructor, *, provider: str, model: str) -> None:
        self.inner = inner
        self.provider = inner.provider
        self.provider_name = provider
        self.model = model

    def create(
        self,
        *,
        response_model: type[T],
        messages: list[ChatCompletionMessageParam],
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
        messages: list[ChatCompletionMessageParam],
        max_tokens: int,
        temperature: float | None = None,
        reasoning: Reasoning | None = None,
    ) -> tuple[T, object]:
        settings = self._settings(max_tokens, temperature, reasoning)
        result, completion = self.inner.create_with_completion(
            response_model=response_model, messages=messages, **settings
        )
        return result, completion

    def _settings(
        self, max_tokens: int, temperature: float | None, reasoning: Reasoning | None
    ) -> dict[str, Any]:
        settings: dict[str, Any] = {"max_tokens": max_tokens}
        if temperature is not None:
            settings["temperature"] = temperature
        if reasoning is None:
            return settings
        if self.provider_name == "openai" and (plan := openai_plan(self.model, reasoning)):
            settings["max_tokens"] = answer_room(max_tokens, plan.room)
            settings["reasoning_effort"] = plan.effort
            if not plan.takes_temperature:
                settings.pop("temperature", None)
        elif self.provider_name == "gemini" and (plan := gemini_plan(self.model, reasoning)):
            settings["max_tokens"] = answer_room(max_tokens, plan.room)
            settings["thinking_config"] = plan.config()
        return settings
