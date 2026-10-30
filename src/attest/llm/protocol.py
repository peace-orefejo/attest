"""The structural type every judge client satisfies: instructor or native Anthropic."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    def create(
        self,
        *,
        response_model: type[T],
        messages: list[ChatCompletionMessageParam],
        max_tokens: int,
        temperature: float,
    ) -> T: ...
