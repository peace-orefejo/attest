"""Compare two benchmark reports: metric deltas per check and per origin, flips, regressions.

A drop in F1 or recall in any binary view beyond the tolerance is a regression, for each check
as a whole and for each origin of a check that mixes origins. An origin is gated only when it
has at least `MIN_ORIGIN_CASES` cases in both reports: below that, one case flipping moves
recall by a tenth or more, so its deltas are shown but don't fail the comparison.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from bench_check_metrics import CheckMetrics
from bench_headline import headline, origin_headline
from bench_report import BenchmarkReport

GATED_METRICS = ("f1", "recall")
"""A drop in either of these, in any binary view, beyond the tolerance is a regression."""
MIN_ORIGIN_CASES = 10
"""An origin needs this many cases in both reports before a drop in it is a regression."""


class MetricDelta(BaseModel):
    old: float | None
    new: float | None
    delta: float | None


Deltas = dict[str, MetricDelta]
"""Metric name -> its change."""


class Flip(BaseModel):
    check: str
    id: str
    old_correct: bool
    new_correct: bool


class Comparison(BaseModel):
    deltas: dict[str, Deltas]
    origin_deltas: dict[str, dict[str, Deltas]] = Field(
        default_factory=dict[str, dict[str, Deltas]]
    )
    """Check -> origin -> metric deltas, for each check whose cases come from more than one
    origin, and each origin in both reports."""
    flips: list[Flip]
    regressions: list[str]
    warnings: list[str] = Field(default_factory=list[str])
    bypassed: list[str] = Field(default_factory=list[str])
    """Compatibility checks that failed and were overridden with --allow-incompatible."""

    @property
    def regressed(self) -> bool:
        return bool(self.regressions)


def compare(
    old: BenchmarkReport,
    new: BenchmarkReport,
    *,
    tolerance: float,
    bypassed: list[str] | None = None,
) -> Comparison:
    """Deltas, flips and regressions. Check compatibility first (`bench_compat`); pass the
    failed checks as `bypassed` when the comparison is forced."""
    deltas: dict[str, Deltas] = {}
    origin_deltas: dict[str, dict[str, Deltas]] = {}
    regressions: list[str] = []
    warnings = _warnings(old, new)
    for check in sorted(old.checks.keys() & new.checks.keys()):
        before, after = old.checks[check], new.checks[check]
        deltas[check] = _deltas(headline(before), headline(after))
        regressions.extend(_regressions(check, deltas[check], tolerance))
        if len(before.per_origin.keys() | after.per_origin.keys()) > 1:
            origin_deltas[check] = _origins(check, before, after, tolerance, regressions, warnings)
    return Comparison(
        deltas=deltas,
        origin_deltas=origin_deltas,
        flips=_flips(old, new),
        regressions=regressions,
        warnings=warnings,
        bypassed=list(bypassed or []),
    )


def _origins(
    check: str,
    before: CheckMetrics,
    after: CheckMetrics,
    tolerance: float,
    regressions: list[str],
    warnings: list[str],
) -> dict[str, Deltas]:
    """Deltas per origin; adds each gated origin's regressions and every caveat in place."""
    by_origin: dict[str, Deltas] = {}
    for origin in sorted(before.per_origin.keys() | after.per_origin.keys()):
        was, now = before.per_origin.get(origin), after.per_origin.get(origin)
        if was is None or now is None:
            warnings.append(f"{check} origin {origin} is in only one report and isn't compared.")
            continue
        by_origin[origin] = _deltas(origin_headline(was), origin_headline(now))
        if min(was.coverage.attempted, now.coverage.attempted) < MIN_ORIGIN_CASES:
            warnings.append(
                f"{check} origin {origin} has fewer than {MIN_ORIGIN_CASES} cases in a report, "
                "so a drop there isn't gated."
            )
            continue
        regressions.extend(_regressions(f"{check} origin {origin}", by_origin[origin], tolerance))
    return by_origin


def _deltas(before: dict[str, float | None], after: dict[str, float | None]) -> Deltas:
    return {name: _delta(before[name], after.get(name)) for name in before}


def _regressions(scope: str, deltas: Deltas, tolerance: float) -> list[str]:
    found: list[str] = []
    for name, change in deltas.items():
        view, _, metric = name.rpartition(".")
        if not view or metric not in GATED_METRICS or change.delta is None:
            continue
        if change.delta < -tolerance:
            found.append(f"{scope} {name} dropped by {-change.delta:.3f}")
    return found


def _delta(old: float | None, new: float | None) -> MetricDelta:
    change = None if old is None or new is None else new - old
    return MetricDelta(old=old, new=new, delta=change)


def _flips(old: BenchmarkReport, new: BenchmarkReport) -> list[Flip]:
    before = {(row.check, row.id): row.correct for row in old.cases}
    flips: list[Flip] = []
    for row in new.cases:
        was = before.get((row.check, row.id))
        if was is not None and row.correct is not None and was != row.correct:
            flips.append(Flip(check=row.check, id=row.id, old_correct=was, new_correct=row.correct))
    return flips


def _warnings(old: BenchmarkReport, new: BenchmarkReport) -> list[str]:
    return [
        f"{check} is in only one report and isn't compared."
        for check in sorted(old.checks.keys() ^ new.checks.keys())
    ]
