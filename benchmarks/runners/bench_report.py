"""The JSON report a benchmark run writes, and its short Markdown summary."""

from __future__ import annotations

from pydantic import BaseModel, Field

from bench_check_metrics import CheckMetrics, Prices
from bench_grade import GradeSettings
from bench_metrics import Rate
from bench_rows import CaseRow

FORMAT_VERSION = 1


class BenchmarkReport(BaseModel):
    format_version: int = FORMAT_VERSION
    dataset_version: str
    attest_version: str
    prompt_version: str
    provider: str
    model: str | None
    split: str
    timestamp: str
    settings: GradeSettings
    prices: Prices = Field(default_factory=Prices)
    complete: bool = True
    stopped_reason: str | None = None
    checks: dict[str, CheckMetrics] = Field(default_factory=dict[str, CheckMetrics])
    skipped_checks: dict[str, str] = Field(default_factory=dict[str, str])
    cases: list[CaseRow] = Field(default_factory=list[CaseRow])


def markdown_summary(report: BenchmarkReport) -> str:
    """A short human summary: one table row per check, then the warnings that matter."""
    lines = [
        f"## attest benchmark: {report.split} split",
        "",
        f"attest {report.attest_version}, prompts {report.prompt_version}, "
        f"{report.provider}/{report.model or 'no model (offline)'}, "
        f"datasets {report.dataset_version[:12]}",
        "",
        "| check | cases | items | accuracy | precision | recall | F1 | FPR | FNR | "
        "median s | tokens |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    lines.extend(_check_line(name, metrics) for name, metrics in report.checks.items())
    lines.append("")
    lines.extend(_warnings(report))
    return "\n".join(lines).rstrip() + "\n"


def _check_line(name: str, metrics: CheckMetrics) -> str:
    found = metrics.detection
    tokens = metrics.usage.input_tokens + metrics.usage.output_tokens
    median = metrics.latency.median_s
    cells = [
        name,
        str(metrics.cases),
        f"{metrics.items} {metrics.item_unit}s",
        _pct(metrics.item_accuracy),
        _pct(found.precision),
        _pct(found.recall),
        "n/a" if found.f1 is None else f"{found.f1:.2f}",
        _pct(found.false_positive_rate),
        _pct(found.false_negative_rate),
        "n/a" if median is None else f"{median:.2f}",
        str(tokens),
    ]
    return "| " + " | ".join(cells) + " |"


def _pct(value: Rate) -> str:
    if value.value is None or value.low is None or value.high is None:
        return "n/a"
    return f"{value.value:.0%} ({value.low:.0%}-{value.high:.0%}, n={value.n})"


def _warnings(report: BenchmarkReport) -> list[str]:
    notes: list[str] = []
    drafts = sum(metrics.draft_cases for metrics in report.checks.values())
    if drafts:
        notes.append(
            f"- {drafts} case(s) carry draft labels. Don't publish these numbers until a "
            "person confirms the labels."
        )
    if report.settings.offline:
        notes.append(
            "- Offline run: no model was called, so tool errors are `unchecked` and injection "
            "is scan-only. These numbers exercise the pipeline; they don't measure attest."
        )
    errored = sum(metrics.errored_cases for metrics in report.checks.values())
    if errored:
        notes.append(f"- {errored} case(s) errored or didn't run and are not scored.")
    if not report.complete:
        notes.append(f"- Incomplete run: {report.stopped_reason}")
    for check, reason in report.skipped_checks.items():
        notes.append(f"- Skipped {check}: {reason}")
    return notes
