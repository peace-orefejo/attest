"""The JSON report a benchmark run writes, and whether its numbers may be published."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, Field

from bench_check_metrics import CheckMetrics, Prices
from bench_grade import GradeSettings
from bench_rows import CaseRow

FORMAT_VERSION = 2
DEFAULT_MIN_COVERAGE = 0.95
"""The share of attempted cases that must be graded, per check, before a number is published."""


class BenchmarkReport(BaseModel):
    format_version: int = FORMAT_VERSION
    dataset_version: str
    dataset_visibility: Literal["public", "private"] = "public"
    """Private: the cases live outside this repository and the report withholds their contents
    (case ids are hashed, claim texts and error messages are removed)."""
    case_id_key: str | None = None
    """For a private report whose case ids were keyed with `ATTEST_BENCH_ID_KEY`, a fingerprint
    of that key (not the key); None when the ids are plain hashes. Rows only match across
    reports with the same value."""
    attest_version: str
    prompt_version: str
    provider: str
    model: str | None
    split: str
    timestamp: str
    settings: GradeSettings
    prices: Prices = Field(default_factory=Prices)
    min_coverage: float = DEFAULT_MIN_COVERAGE
    budget_exhausted: bool = False
    """The call budget ran out, so some cases were not run."""
    all_cases_graded: bool = True
    """Every case of every check that ran was graded: none errored and none was skipped."""
    stopped_reason: str | None = None
    publishable: bool = False
    not_publishable_because: list[str] = Field(default_factory=list[str])
    checks: dict[str, CheckMetrics] = Field(default_factory=dict[str, CheckMetrics])
    skipped_checks: dict[str, str] = Field(default_factory=dict[str, str])
    cases: list[CaseRow] = Field(default_factory=list[CaseRow])


def publishability(
    checks: Mapping[str, CheckMetrics],
    *,
    settings: GradeSettings,
    budget_exhausted: bool,
    min_coverage: float,
) -> list[str]:
    """Why these numbers may not be published; empty when they may."""
    reasons: list[str] = []
    drafts = sum(metrics.draft_cases for metrics in checks.values())
    if drafts:
        reasons.append(f"{drafts} case(s) carry draft labels")
    for name, metrics in checks.items():
        share = metrics.coverage.coverage.value
        if share is not None and share < min_coverage:
            reasons.append(f"{name} coverage {share:.1%} is below the minimum {min_coverage:.0%}")
    if budget_exhausted:
        reasons.append("the call budget ran out")
    if settings.offline:
        reasons.append("offline run: no model was called")
    if not checks:
        reasons.append("no check ran")
    return reasons
