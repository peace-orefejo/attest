"""Send one structured request to a client, with a reasoning level when the client takes one.

Every response the provider billed is counted in `Usage`, including one that failed: a cut-off
or unparseable answer still used its tokens, so a `Budget` must see them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol, TypeGuard, TypeVar

from pydantic import BaseModel

from .budget import record_completion
from .errors import failed_completions
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
    try:
        result, completion = _send(client, output, max_tokens, messages, reasoning)
    except Exception as error:
        for billed in failed_completions(error):
            record_completion(billed)
        raise
    record_completion(completion)
    return result


def _send(
    client: LLMClient,
    output: type[T],
    max_tokens: int,
    messages: list[ChatCompletionMessageParam],
    reasoning: Reasoning,
) -> tuple[T, object]:
    if takes_reasoning(client):
        return client.create_with_completion(
            response_model=output,
            max_tokens=max_tokens,
            temperature=0,
            messages=messages,
            reasoning=reasoning,
        )
    with_completion = getattr(client, "create_with_completion", None)
    if with_completion is None:
        answer = client.create(
            response_model=output, max_tokens=max_tokens, temperature=0, messages=messages
        )
        return answer, None
    return with_completion(
        response_model=output, max_tokens=max_tokens, temperature=0, messages=messages
    )
