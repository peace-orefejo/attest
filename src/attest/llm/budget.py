"""Spend accounting and hard limits for judge calls, so a run never silently burns tokens."""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from contextvars import ContextVar

from pydantic import BaseModel, computed_field

from .usage import TokenCounts, token_counts

CHARS_PER_TOKEN = 4


class BudgetExceeded(RuntimeError):
    """Raised before a judge call that would take the run past its budget."""


class Usage(BaseModel):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_hits: int = 0

    @computed_field
    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def as_dict(self) -> dict[str, int]:
        return self.model_dump()

    def since(self, before: Usage) -> Usage:
        return Usage(
            calls=self.calls - before.calls,
            input_tokens=self.input_tokens - before.input_tokens,
            output_tokens=self.output_tokens - before.output_tokens,
            cached_input_tokens=self.cached_input_tokens - before.cached_input_tokens,
            cache_write_tokens=self.cache_write_tokens - before.cache_write_tokens,
            cache_hits=self.cache_hits - before.cache_hits,
        )

    def add_tokens(self, counts: TokenCounts) -> None:
        self.input_tokens += counts.input
        self.output_tokens += counts.output
        self.cached_input_tokens += counts.cached
        self.cache_write_tokens += counts.written


class Budget(BaseModel):
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


class _Meter(BaseModel):
    usage: Usage
    budget: Budget | None = None


_meter: ContextVar[_Meter | None] = ContextVar("attest_meter", default=None)


@contextlib.contextmanager
def metering(usage: Usage, budget: Budget | None = None) -> Generator[None]:
    token = _meter.set(_Meter.model_construct(usage=usage, budget=budget))
    try:
        yield
    finally:
        _meter.reset(token)


def estimate_tokens(*texts: str) -> int:
    return sum(len(text) for text in texts) // CHARS_PER_TOKEN + 1


def before_call(*texts: str) -> None:
    meter = _meter.get()
    if meter is None:
        return
    if meter.budget is not None:
        meter.budget.check(meter.usage, estimated_input=estimate_tokens(*texts))
    meter.usage.calls += 1


def record_cache_hit() -> None:
    meter = _meter.get()
    if meter is not None:
        meter.usage.cache_hits += 1


def record_completion(completion: object) -> None:
    meter = _meter.get()
    if meter is None or completion is None:
        return
    meter.usage.add_tokens(token_counts(completion))
