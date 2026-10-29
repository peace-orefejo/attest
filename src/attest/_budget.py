"""Spend accounting and hard limits for judge calls, so a run never silently burns tokens."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any

_CHARS_PER_TOKEN = 4


class BudgetExceeded(RuntimeError):
    """Raised before a judge call that would take the run past its budget."""


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_hits: int = 0

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def as_dict(self) -> dict:
        return {**asdict(self), "tokens": self.tokens}

    def since(self, before: Usage) -> Usage:
        return Usage(
            calls=self.calls - before.calls,
            input_tokens=self.input_tokens - before.input_tokens,
            output_tokens=self.output_tokens - before.output_tokens,
            cached_input_tokens=self.cached_input_tokens - before.cached_input_tokens,
            cache_write_tokens=self.cache_write_tokens - before.cache_write_tokens,
            cache_hits=self.cache_hits - before.cache_hits,
        )

    def copy(self) -> Usage:
        return Usage(**asdict(self))


@dataclass
class Budget:
    """Ceilings for one Attest instance. `None` means unlimited."""

    max_calls: int | None = None
    max_tokens: int | None = None

    def check(self, usage: Usage, *, estimated_input: int) -> None:
        if self.max_calls is not None and usage.calls + 1 > self.max_calls:
            raise BudgetExceeded(
                f"Call budget exhausted: {usage.calls}/{self.max_calls} judge calls used."
            )
        if self.max_tokens is not None and usage.tokens + estimated_input > self.max_tokens:
            raise BudgetExceeded(
                f"Token budget exhausted: {usage.tokens} used, next call needs about "
                f"{estimated_input} input tokens, limit is {self.max_tokens}."
            )


_meter: ContextVar[tuple[Usage, Budget | None] | None] = ContextVar("attest_meter", default=None)


@contextlib.contextmanager
def metering(usage: Usage, budget: Budget | None = None) -> Iterator[None]:
    token = _meter.set((usage, budget))
    try:
        yield
    finally:
        _meter.reset(token)


def estimate_tokens(*texts: str) -> int:
    return sum(len(t) for t in texts) // _CHARS_PER_TOKEN + 1


def before_call(*texts: str) -> None:
    active = _meter.get()
    if active is None:
        return
    usage, budget = active
    if budget is not None:
        budget.check(usage, estimated_input=estimate_tokens(*texts))
    usage.calls += 1


def record_cache_hit() -> None:
    active = _meter.get()
    if active is not None:
        active[0].cache_hits += 1


def record_completion(completion: Any) -> None:
    active = _meter.get()
    if active is None or completion is None:
        return
    usage = active[0]
    counts = token_counts(completion)
    usage.input_tokens += counts.input
    usage.output_tokens += counts.output
    usage.cached_input_tokens += counts.cached
    usage.cache_write_tokens += counts.written


@dataclass(frozen=True)
class TokenCounts:
    input: int = 0
    output: int = 0
    cached: int = 0
    written: int = 0


def _n(obj: Any, *names: str) -> int:
    for name in names:
        value = getattr(obj, name, None)
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def token_counts(completion: Any) -> TokenCounts:
    """Normalize Anthropic / OpenAI / Gemini usage. `input` always includes cached tokens."""
    usage = getattr(completion, "usage", None)
    if usage is not None and hasattr(usage, "input_tokens"):
        cached = _n(usage, "cache_read_input_tokens")
        written = _n(usage, "cache_creation_input_tokens")
        return TokenCounts(
            input=_n(usage, "input_tokens") + cached + written,
            output=_n(usage, "output_tokens"),
            cached=cached,
            written=written,
        )
    if usage is not None:
        details = getattr(usage, "prompt_tokens_details", None)
        return TokenCounts(
            input=_n(usage, "prompt_tokens"),
            output=_n(usage, "completion_tokens"),
            cached=_n(details, "cached_tokens"),
        )
    meta = getattr(completion, "usage_metadata", None)
    if meta is not None:
        return TokenCounts(
            input=_n(meta, "prompt_token_count"),
            output=_n(meta, "candidates_token_count"),
            cached=_n(meta, "cached_content_token_count"),
        )
    return TokenCounts()
