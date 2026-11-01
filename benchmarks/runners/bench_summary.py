"""The short Markdown summary a benchmark run prints."""

from __future__ import annotations

from collections import Counter

from bench_check_metrics import BinaryMetrics, CategoryMetrics, CheckMetrics
from bench_metrics import Rate
from bench_report import BenchmarkReport

FAITHFULNESS_SCOPE = (
    "- Faithfulness cases supply their labelled claims through a fixed extractor, so these "
    "numbers measure the verifier's judgement of each claim and **not** claim extraction."
)
READING_GUIDE = (
    "Graded-only figures count graded cases; effective figures count every attempted case, "
    "with errored and not-run items as wrong or missed. Coverage is graded / attempted."
)


def markdown_summary(report: BenchmarkReport) -> str:
    """One accuracy row per check and one row per binary view, each beside its coverage."""
    lines = [
        f"## attest benchmark: {report.split} split",
        "",
        f"attest {report.attest_version}, prompts {report.prompt_version}, "
        f"{report.provider}/{report.model or 'no model (offline)'}, "
        f"datasets {report.dataset_version[:12]}",
        "",
        _origin_counts(report),
        "",
        *_private_note(report),
        *_publish_banner(report),
        READING_GUIDE,
        "",
        "| check | coverage | errored | not run | item accuracy (graded only) | "
        "item accuracy (effective) | cases correct (graded only) | cases correct (effective) | "
        "median s | tokens |",
        "|---|---|---|---|---|---|---|---|---|---|",
        *(_accuracy_line(name, metrics) for name, metrics in report.checks.items()),
        "",
        "| check | binary view | positive | coverage | precision | recall (graded only) | "
        "recall (effective) | F1 | FPR | FNR |",
        "|---|---|---|---|---|---|---|---|---|---|",
        *(
            _view_line(name, view_name, view, metrics)
            for name, metrics in report.checks.items()
            for view_name, view in metrics.binary.items()
        ),
        "",
        *_origin_table(report),
        *_notes(report),
    ]
    return "\n".join(lines).rstrip() + "\n"


def _publish_banner(report: BenchmarkReport) -> list[str]:
    if report.publishable:
        return []
    return [
        "> **NOT PUBLISHABLE.** " + "; ".join(report.not_publishable_because) + ".",
        "",
    ]


def _accuracy_line(name: str, metrics: CheckMetrics) -> str:
    covered = metrics.coverage
    median = metrics.latency.median_s
    cells = [
        name,
        _coverage(metrics),
        str(covered.errored),
        str(covered.not_run),
        _pct(metrics.item_accuracy),
        _pct(metrics.effective.item_accuracy),
        _pct(metrics.case_accuracy),
        _pct(metrics.effective.case_accuracy),
        "n/a" if median is None else f"{median:.2f}",
        str(metrics.usage.input_tokens + metrics.usage.output_tokens),
    ]
    return "| " + " | ".join(cells) + " |"


def _view_line(name: str, view_name: str, view: BinaryMetrics, metrics: CheckMetrics) -> str:
    cells = [
        name,
        view_name,
        " + ".join(view.positive),
        _coverage(metrics),
        _pct(view.precision),
        _pct(view.recall),
        _pct(view.effective_recall),
        "n/a" if view.f1 is None else f"{view.f1:.2f}",
        _pct(view.false_positive_rate),
        _pct(view.false_negative_rate),
    ]
    return "| " + " | ".join(cells) + " |"


def _origin_counts(report: BenchmarkReport) -> str:
    counts = Counter(row.origin or "unknown" for row in report.cases)
    listed = ", ".join(f"{origin} {n}" for origin, n in sorted(counts.items()))
    return f"Cases by origin: {listed or 'none'}."


def _origin_table(report: BenchmarkReport) -> list[str]:
    """Coverage and accuracy per origin, only when some check mixes origins."""
    if all(len(metrics.per_origin) < 2 for metrics in report.checks.values()):
        return []
    return [
        "| check | origin | coverage | item accuracy (graded only) | item accuracy (effective) |",
        "|---|---|---|---|---|",
        *(
            _origin_line(name, origin, group)
            for name, metrics in report.checks.items()
            for origin, group in metrics.per_origin.items()
        ),
        "",
    ]


def _origin_line(name: str, origin: str, group: CategoryMetrics) -> str:
    cells = [
        name,
        origin,
        _coverage(group),
        _pct(group.item_accuracy),
        _pct(group.effective.item_accuracy),
    ]
    return "| " + " | ".join(cells) + " |"


def _coverage(metrics: CheckMetrics | CategoryMetrics) -> str:
    covered, share = metrics.coverage, metrics.coverage.coverage
    if share.value is None or share.low is None or share.high is None:
        return "n/a (0 cases)"
    return (
        f"{share.value:.0%} {covered.graded}/{covered.attempted} ({share.low:.0%}-{share.high:.0%})"
    )


def _pct(value: Rate) -> str:
    if value.value is None or value.low is None or value.high is None:
        return "n/a"
    return f"{value.value:.0%} ({value.low:.0%}-{value.high:.0%}, n={value.n})"


def _notes(report: BenchmarkReport) -> list[str]:
    notes: list[str] = []
    if "faithfulness" in report.checks or "faithfulness" in report.skipped_checks:
        notes.append(FAITHFULNESS_SCOPE)
    if "faithfulness" in report.checks:
        notes.append(
            "- Faithfulness `contradiction_detection` counts only `unsupported` as positive; "
            "`evidence_sufficiency` also counts `unverifiable`. Only the first measures "
            "whether attest detects contradictions."
        )
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
    for name, metrics in report.checks.items():
        share = metrics.coverage.coverage.value
        if share is not None and share < report.min_coverage:
            notes.append(
                f"- WARNING: {name} coverage is {share:.0%}, below the {report.min_coverage:.0%} "
                f"minimum ({metrics.coverage.errored} errored, {metrics.coverage.not_run} not "
                "run). Its graded-only figures overstate accuracy; read the effective ones."
            )
    if report.budget_exhausted:
        notes.append(f"- Budget exhausted: {report.stopped_reason}")
    for check, reason in report.skipped_checks.items():
        notes.append(f"- Skipped {check}: {reason}")
    return notes


def _private_note(report: BenchmarkReport) -> list[str]:
    if report.dataset_visibility != "private":
        return []
    return [
        "> **Private dataset.** The cases aren't in this repository, and this report withholds "
        "their contents: case ids are hashed, claim texts and error messages removed. Others "
        "can't reproduce these numbers.",
        "",
    ]
