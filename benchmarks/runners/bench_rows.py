"""What grading one case produces: a row per case, an item per labelled claim, call or run."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from attest import Usage

MISSING = "missing"
"""The prediction for a labelled item attest returned no finding for."""
ERROR = "error"
"""The prediction for every item of a case whose evaluation raised."""
NOT_RUN = "not_run"
"""The prediction for every item of a case skipped because the call budget ran out."""
UNGRADED_PREDICTIONS = frozenset({MISSING, ERROR, NOT_RUN})
"""Predictions that never count as a detection in a binary view."""

CaseStatus = Literal["graded", "errored", "not_run"]


class Item(BaseModel):
    """One labelled unit: a claim (faithfulness), a tool call (tool_use, recovery) or a run."""

    key: str
    expected: str
    predicted: str
    correct: bool


class CaseUsage(BaseModel):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cache_hits: int = 0

    @classmethod
    def from_usage(cls, usage: Usage) -> CaseUsage:
        return cls(
            calls=usage.calls,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            cache_hits=usage.cache_hits,
        )


class CaseRow(BaseModel):
    """The result of one case. `correct` is None when the case errored or didn't run; such a
    row still lists its labelled items, predicted `error` or `not_run`, so effective metrics
    can count them as wrong."""

    id: str
    check: str
    category: str
    source: str
    label_status: str
    status: CaseStatus = "graded"
    items: list[Item] = Field(default_factory=list[Item])
    correct: bool | None = None
    verdict: str | None = None
    run_expected: str | None = None
    run_predicted: str | None = None
    latency_s: float | None = None
    usage: CaseUsage = Field(default_factory=CaseUsage)
    error: str | None = None

    @property
    def graded(self) -> bool:
        return self.status == "graded"


def item(key: str, expected: str, predicted: str) -> Item:
    return Item(key=key, expected=expected, predicted=predicted, correct=expected == predicted)
