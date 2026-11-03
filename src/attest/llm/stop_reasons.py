"""Whether a provider response stopped at its output-token limit, for each provider's shape."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

ANTHROPIC_LIMIT = "max_tokens"
OPENAI_LIMIT = "length"
GEMINI_LIMIT = "MAX_TOKENS"


def stopped_at_limit(completion: object) -> bool:
    """Anthropic's `stop_reason`, OpenAI's `finish_reason` or Gemini's `finish_reason` says the
    response hit `max_tokens`."""
    if getattr(completion, "stop_reason", None) == ANTHROPIC_LIMIT:
        return True
    choice = _first(completion, "choices")
    if choice is not None:
        return getattr(choice, "finish_reason", None) == OPENAI_LIMIT
    candidate = _first(completion, "candidates")
    if candidate is not None:
        reason = getattr(candidate, "finish_reason", None)
        return getattr(reason, "value", reason) == GEMINI_LIMIT
    return False


def _first(completion: object, name: str) -> object | None:
    items = getattr(completion, name, None)
    if not isinstance(items, Sequence) or isinstance(items, str):
        return None
    listed = cast("Sequence[object]", items)
    return listed[0] if listed else None
