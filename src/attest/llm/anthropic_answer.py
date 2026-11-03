"""Read the structured answer out of a Claude message, telling a cut-off answer from a bad one."""

from __future__ import annotations

from typing import TypeVar

from anthropic.types import Message
from pydantic import BaseModel, ValidationError

from .errors import TruncatedOutput, UnreadableOutput
from .stop_reasons import ANTHROPIC_LIMIT

T = TypeVar("T", bound=BaseModel)


def structured_answer(response: Message, output: type[T], model: str) -> T:
    """The first text block as an `output`, or an error that carries the billed `response`.

    A message stopped at `max_tokens` raises `TruncatedOutput`, whether its JSON is partial or
    missing, so it is never retried. Any other unreadable answer raises `UnreadableOutput`.
    """
    cut_off = response.stop_reason == ANTHROPIC_LIMIT
    error_type = TruncatedOutput if cut_off else UnreadableOutput
    message = (
        f"{model} returned no structured output (stop_reason={response.stop_reason!r}). "
        "Try a larger max_tokens or a different model."
    )
    text = next((block.text for block in response.content if block.type == "text"), None)
    if text is None:
        raise error_type(message, completion=response)
    try:
        return output.model_validate_json(text)
    except ValidationError as error:
        raise error_type(message, completion=response) from error
