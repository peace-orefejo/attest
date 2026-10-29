"""Normalize provider usage metadata (Anthropic, OpenAI, Gemini) into one token count shape."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TokenCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    input: int = 0
    output: int = 0
    cached: int = 0
    written: int = 0


def token_counts(completion: object) -> TokenCounts:
    """Normalize provider usage. `input` always includes cached tokens."""
    usage = getattr(completion, "usage", None)
    if usage is not None and hasattr(usage, "input_tokens"):
        return _anthropic_counts(usage)
    if usage is not None:
        return _openai_counts(usage)
    meta = getattr(completion, "usage_metadata", None)
    if meta is not None:
        return _gemini_counts(meta)
    return TokenCounts()


def _anthropic_counts(usage: object) -> TokenCounts:
    cached = _int_attr(usage, "cache_read_input_tokens")
    written = _int_attr(usage, "cache_creation_input_tokens")
    return TokenCounts(
        input=_int_attr(usage, "input_tokens") + cached + written,
        output=_int_attr(usage, "output_tokens"),
        cached=cached,
        written=written,
    )


def _openai_counts(usage: object) -> TokenCounts:
    details = getattr(usage, "prompt_tokens_details", None)
    return TokenCounts(
        input=_int_attr(usage, "prompt_tokens"),
        output=_int_attr(usage, "completion_tokens"),
        cached=_int_attr(details, "cached_tokens"),
    )


def _gemini_counts(meta: object) -> TokenCounts:
    return TokenCounts(
        input=_int_attr(meta, "prompt_token_count"),
        output=_int_attr(meta, "candidates_token_count"),
        cached=_int_attr(meta, "cached_content_token_count"),
    )


def _int_attr(obj: object, name: str) -> int:
    value = getattr(obj, name, None)
    if isinstance(value, int | float):
        return int(value)
    return 0
