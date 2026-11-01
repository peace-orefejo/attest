"""Whether two benchmark reports can be compared like for like."""

from __future__ import annotations

from bench_report import BenchmarkReport


def incompatibilities(
    old: BenchmarkReport,
    new: BenchmarkReport,
    *,
    min_coverage: float,
    allow_model_change: bool = False,
) -> list[str]:
    """Every reason the two reports aren't like for like; empty when they are."""
    reasons = _setup_differences(old, new, allow_model_change=allow_model_change)
    for report, name in ((old, "old"), (new, "new")):
        reasons.extend(_coverage_problems(report, name, min_coverage))
    return reasons


def _setup_differences(
    old: BenchmarkReport, new: BenchmarkReport, *, allow_model_change: bool
) -> list[str]:
    reasons: list[str] = []
    if old.dataset_version != new.dataset_version:
        reasons.append(
            f"dataset versions differ ({old.dataset_version[:12]} vs "
            f"{new.dataset_version[:12]}): the cases or labels changed"
        )
    if old.dataset_visibility != new.dataset_visibility:
        reasons.append(
            f"one report is on a public dataset and the other on a private one "
            f"({old.dataset_visibility} vs {new.dataset_visibility})"
        )
    elif old.case_id_key != new.case_id_key:
        reasons.append(
            "the private case ids were hashed differently (a different ATTEST_BENCH_ID_KEY, "
            "or a key in only one report), so no case could be matched"
        )
    if old.split != new.split:
        reasons.append(f"splits differ ({old.split} vs {new.split})")
    before, after = old.settings.model_dump(), new.settings.model_dump()
    for field in sorted(before.keys() | after.keys()):
        if before.get(field) != after.get(field):
            reasons.append(
                f"setting {field} differs ({before.get(field)!r} vs {after.get(field)!r})"
            )
    if old.provider != new.provider:
        reasons.append(f"providers differ ({old.provider} vs {new.provider})")
    if old.model != new.model and not allow_model_change:
        reasons.append(
            f"models differ ({old.model} vs {new.model}); pass --allow-model-change if that "
            "is the point of the comparison"
        )
    return reasons


def _coverage_problems(report: BenchmarkReport, name: str, min_coverage: float) -> list[str]:
    reasons: list[str] = []
    if report.budget_exhausted:
        reasons.append(f"the {name} report ran out of budget: {report.stopped_reason}")
    if not report.cases:
        reasons.append(f"the {name} report has no cases")
    elif not report.all_cases_graded:
        reasons.append(f"the {name} report has cases that errored or didn't run")
    for check, metrics in sorted(report.checks.items()):
        share = metrics.coverage.coverage.value
        if share is not None and share < min_coverage:
            reasons.append(
                f"{check} coverage in the {name} report is {share:.1%}, below {min_coverage:.0%}"
            )
    return reasons
