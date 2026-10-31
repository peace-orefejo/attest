"""Compare two benchmark reports: metric deltas per check, flipped cases, regressions."""

from __future__ import annotations

from pydantic import BaseModel, Field

from bench_check_metrics import CheckMetrics
from bench_report import BenchmarkReport

GATED_METRICS = ("f1", "recall")
"""A drop in either of these beyond the tolerance is a regression."""


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

    @property
    def regressed(self) -> bool:
        return bool(self.regressions)


def headline(metrics: CheckMetrics) -> dict[str, float | None]:
    """The metrics compare reports on, by name."""
    found = metrics.detection
    values: dict[str, float | None] = {
        "item_accuracy": metrics.item_accuracy.value,
        "case_accuracy": metrics.case_accuracy.value,
        "precision": found.precision.value,
        "recall": found.recall.value,
        "f1": found.f1,
        "false_positive_rate": found.false_positive_rate.value,
        "false_negative_rate": found.false_negative_rate.value,
        "latency_median_s": metrics.latency.median_s,
        "tokens_per_case": metrics.usage.tokens_per_case,
    }
    if metrics.claim_coverage is not None:
        values["claim_coverage"] = metrics.claim_coverage.value
    return values


def compare(old: BenchmarkReport, new: BenchmarkReport, *, tolerance: float) -> Comparison:
    deltas: dict[str, dict[str, MetricDelta]] = {}
    regressions: list[str] = []
    for check in sorted(old.checks.keys() & new.checks.keys()):
        before, after = headline(old.checks[check]), headline(new.checks[check])
        deltas[check] = {name: _delta(before[name], after.get(name)) for name in before}
        for name in GATED_METRICS:
            change = deltas[check][name].delta
            if change is not None and change < -tolerance:
                regressions.append(f"{check} {name} dropped by {-change:.3f}")
    return Comparison(
        deltas=deltas,
        flips=_flips(old, new),
        regressions=regressions,
        warnings=_warnings(old, new),
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
    notes: list[str] = []
    if old.dataset_version != new.dataset_version:
        notes.append("Dataset versions differ: the cases or labels changed between runs.")
    if old.split != new.split:
        notes.append(f"Different splits: {old.split} vs {new.split}.")
    if old.settings != new.settings:
        notes.append("Run settings differ (offline, answer kind or tool-choice check).")
    for check in sorted(old.checks.keys() ^ new.checks.keys()):
        notes.append(f"{check} is in only one report and isn't compared.")
    for report, name in ((old, "old"), (new, "new")):
        if not report.complete:
            notes.append(f"The {name} report is incomplete: {report.stopped_reason}")
    return notes


def format_comparison(comparison: Comparison) -> str:
    lines: list[str] = []
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


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _signed(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.3f}"


def _mark(correct: bool) -> str:
    return "correct" if correct else "wrong"
