"""Compare two benchmark reports: metric deltas per check, flipped cases, regressions."""

from __future__ import annotations

from pydantic import BaseModel, Field

from bench_check_metrics import CheckMetrics
from bench_report import BenchmarkReport

GATED_METRICS = ("f1", "recall")
"""A drop in either of these, in any binary view, beyond the tolerance is a regression."""


class MetricDelta(BaseModel):
    old: float | None
    new: float | None
    delta: float | None


class Flip(BaseModel):
    check: str
    id: str
    old_correct: bool
    new_correct: bool


class Comparison(BaseModel):
    deltas: dict[str, dict[str, MetricDelta]]
    flips: list[Flip]
    regressions: list[str]
    warnings: list[str] = Field(default_factory=list[str])
    bypassed: list[str] = Field(default_factory=list[str])
    """Compatibility checks that failed and were overridden with --allow-incompatible."""

    @property
    def regressed(self) -> bool:
        return bool(self.regressions)


def headline(metrics: CheckMetrics) -> dict[str, float | None]:
    """The metrics compare reports on, by name. Binary-view metrics are `<view>.<metric>`."""
    values: dict[str, float | None] = {
        "coverage": metrics.coverage.coverage.value,
        "item_accuracy": metrics.item_accuracy.value,
        "effective_item_accuracy": metrics.effective.item_accuracy.value,
        "case_accuracy": metrics.case_accuracy.value,
    }
    for name, view in metrics.binary.items():
        values[f"{name}.precision"] = view.precision.value
        values[f"{name}.recall"] = view.recall.value
        values[f"{name}.effective_recall"] = view.effective_recall.value
        values[f"{name}.f1"] = view.f1
        values[f"{name}.false_positive_rate"] = view.false_positive_rate.value
        values[f"{name}.false_negative_rate"] = view.false_negative_rate.value
    values["latency_median_s"] = metrics.latency.median_s
    values["tokens_per_case"] = metrics.usage.tokens_per_case
    if metrics.claim_coverage is not None:
        values["claim_coverage"] = metrics.claim_coverage.value
    return values


def compare(
    old: BenchmarkReport,
    new: BenchmarkReport,
    *,
    tolerance: float,
    bypassed: list[str] | None = None,
) -> Comparison:
    """Deltas, flips and regressions. Check compatibility first (`bench_compat`); pass the
    failed checks as `bypassed` when the comparison is forced."""
    deltas: dict[str, dict[str, MetricDelta]] = {}
    regressions: list[str] = []
    for check in sorted(old.checks.keys() & new.checks.keys()):
        before, after = headline(old.checks[check]), headline(new.checks[check])
        deltas[check] = {name: _delta(before[name], after.get(name)) for name in before}
        for name, change in deltas[check].items():
            view, _, metric = name.rpartition(".")
            if (
                view
                and metric in GATED_METRICS
                and change.delta is not None
                and change.delta < -tolerance
            ):
                regressions.append(f"{check} {name} dropped by {-change.delta:.3f}")
    return Comparison(
        deltas=deltas,
        flips=_flips(old, new),
        regressions=regressions,
        warnings=_warnings(old, new),
        bypassed=list(bypassed or []),
    )


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


def format_comparison(comparison: Comparison) -> str:
    lines = _bypass_banner(comparison.bypassed)
    for check, metrics in comparison.deltas.items():
        lines.append(f"## {check}")
        lines.append("| metric | old | new | delta |")
        lines.append("|---|---|---|---|")
        lines.extend(
            f"| {name} | {_num(d.old)} | {_num(d.new)} | {_signed(d.delta)} |"
            for name, d in metrics.items()
        )
        lines.append("")
    if comparison.flips:
        lines.append("## Flipped cases")
        lines.extend(
            f"- {f.check} {f.id}: {_mark(f.old_correct)} -> {_mark(f.new_correct)}"
            for f in comparison.flips
        )
        lines.append("")
    lines.extend(f"- warning: {note}" for note in comparison.warnings)
    lines.extend(f"- REGRESSION: {note}" for note in comparison.regressions)
    if not comparison.regressions:
        lines.append("No regressions beyond the tolerance.")
    return "\n".join(lines).rstrip() + "\n"


def _bypass_banner(bypassed: list[str]) -> list[str]:
    if not bypassed:
        return []
    return [
        "!!! FORCED COMPARISON (--allow-incompatible): these reports are NOT like for like. "
        "Bypassed checks:",
        *(f"!!! - {reason}" for reason in bypassed),
        "",
    ]


def format_refusal(reasons: list[str]) -> str:
    """Why compare refused, with no metric deltas."""
    lines = ["Refusing to compare: the reports are not like for like.", ""]
    lines.extend(f"- {reason}" for reason in reasons)
    lines.append("")
    lines.append("Fix the runs, or pass --allow-incompatible to compare them anyway.")
    return "\n".join(lines) + "\n"


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _signed(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.3f}"


def _mark(correct: bool) -> str:
    return "correct" if correct else "wrong"
