"""Send one structured request to a client, with a reasoning level when the client takes one."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol, TypeGuard, TypeVar

from pydantic import BaseModel

from .budget import record_completion
from .protocol import LLMClient
from .reasoning import Reasoning

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam

T = TypeVar("T", bound=BaseModel)


class ReasoningClient(Protocol):
    """A client attest built for a known provider, which turns a level into provider settings."""

    supports_reasoning: Literal[True]

    def create_with_completion(
        self,
        *,
        response_model: type[T],
        messages: list[ChatCompletionMessageParam],
        max_tokens: int,
        temperature: float | None = None,
        reasoning: Reasoning | None = None,
    ) -> tuple[T, object]: ...


def takes_reasoning(client: LLMClient) -> TypeGuard[ReasoningClient]:
    """Only attest's own provider clients get a level; a custom client's calls are unchanged."""
    return getattr(client, "supports_reasoning", False) is True


def create(
    client: LLMClient,
    output: type[T],
    max_tokens: int,
    messages: list[ChatCompletionMessageParam],
    reasoning: Reasoning,
) -> T:
    if takes_reasoning(client):
        result, completion = client.create_with_completion(
            response_model=output,
            max_tokens=max_tokens,
            temperature=0,
            messages=messages,
            reasoning=reasoning,
        )
        record_completion(completion)
        return result
    with_completion = getattr(client, "create_with_completion", None)
    if with_completion is None:
        return client.create(
            response_model=output, max_tokens=max_tokens, temperature=0, messages=messages
        )
    result, completion = with_completion(
        response_model=output, max_tokens=max_tokens, temperature=0, messages=messages
    )
    record_completion(completion)
    return result
