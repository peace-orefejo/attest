"""Grade every case of the chosen checks and split, timing each one and metering its usage."""

from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import UTC, datetime

import attest
from attest import PROMPT_VERSION, Attest, BudgetExceeded
from bench_cases import (
    Case,
    CheckName,
    FaithfulnessExpected,
    RecoveryExpected,
    Split,
    ToolUseExpected,
)
from bench_check_metrics import Prices, check_metrics
from bench_grade import GRADERS, OFFLINE_CHECKS, GradeSettings
from bench_load import Datasets
from bench_report import DEFAULT_MIN_COVERAGE, BenchmarkReport, publishability
from bench_rows import ERROR, NOT_RUN, CaseRow, CaseUsage, Item, item


class BudgetStop(Exception):
    """The call budget ran out; the remaining cases are recorded as not run."""


def run_benchmark(
    judge: Attest,
    datasets: Datasets,
    *,
    checks: Sequence[CheckName],
    split: Split,
    settings: GradeSettings,
    prices: Prices | None = None,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> BenchmarkReport:
    """Grade `checks` on `split`. Offline, checks that need a model are skipped, not faked."""
    runnable: list[CheckName] = [c for c in checks if not settings.offline or c in OFFLINE_CHECKS]
    skipped = {c: "needs a model; run without --offline" for c in checks if c not in runnable}
    rows: dict[CheckName, list[CaseRow]] = {}
    stopped: str | None = None
    for check in runnable:
        rows[check] = []
        for case in datasets.split(check, split):
            if stopped is not None:
                rows[check].append(_not_run(case, stopped))
                continue
            try:
                rows[check].append(grade_case(judge, case, settings))
            except BudgetStop as exc:
                stopped = str(exc)
                rows[check].append(_not_run(case, stopped))
    all_rows = [row for check_rows in rows.values() for row in check_rows]
    price = prices or Prices()
    metrics = {check: check_metrics(check, check_rows, price) for check, check_rows in rows.items()}
    blockers = publishability(
        metrics,
        split=split,
        settings=settings,
        budget_exhausted=stopped is not None,
        min_coverage=min_coverage,
    )
    return BenchmarkReport(
        dataset_version=datasets.version,
        attest_version=attest.__version__,
        prompt_version=PROMPT_VERSION,
        provider=judge.provider,
        model=None if settings.offline else judge.model,
        split=split,
        timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
        settings=settings,
        prices=price,
        min_coverage=min_coverage,
        budget_exhausted=stopped is not None,
        all_cases_graded=bool(all_rows) and all(row.graded for row in all_rows),
        stopped_reason=stopped,
        publishable=not blockers,
        not_publishable_because=blockers,
        checks=metrics,
        skipped_checks=skipped,
        cases=all_rows,
    )


def grade_case(judge: Attest, case: Case, settings: GradeSettings) -> CaseRow:
    """Grade one case. A failure becomes an errored row; a spent budget raises BudgetStop."""
    row = _blank_row(case)
    before = judge.usage.model_copy()
    started = time.perf_counter()
    try:
        graded = GRADERS[case.check](judge, case, settings)
    except BudgetExceeded as exc:
        raise BudgetStop(f"budget exhausted at case {case.id!r}: {exc}") from exc
    except Exception as exc:
        row.status = "errored"
        row.error = f"{type(exc).__name__}: {exc}"
        row.items = ungraded_items(case, ERROR)
        row.usage = CaseUsage.from_usage(judge.usage.since(before))
        return row
    row.latency_s = time.perf_counter() - started
    row.usage = CaseUsage.from_usage(judge.usage.since(before))
    row.items = graded.items
    row.correct = all(item.correct for item in graded.items)
    row.verdict = graded.verdict
    row.run_expected = graded.run_expected
    row.run_predicted = graded.run_predicted
    return row


def _blank_row(case: Case) -> CaseRow:
    return CaseRow(
        id=case.id,
        check=case.check,
        category=case.category,
        source=case.source,
        origin=case.origin,
        label_status=case.label_status,
    )


def _not_run(case: Case, reason: str) -> CaseRow:
    row = _blank_row(case)
    row.status = "not_run"
    row.error = f"not run: {reason}"
    row.items = ungraded_items(case, NOT_RUN)
    return row


def ungraded_items(case: Case, predicted: str) -> list[Item]:
    """Every labelled item of a case that wasn't graded, with one placeholder prediction."""
    expected = case.expected
    labels: list[tuple[str, str]]
    if isinstance(expected, FaithfulnessExpected):
        labels = [(claim.text, claim.label) for claim in expected.claims]
    elif isinstance(expected, RecoveryExpected):
        labels = [(f"step {call.step}", call.recovery) for call in expected.calls]
    elif isinstance(expected, ToolUseExpected):
        labels = [(f"step {call.step}", call.verdict) for call in expected.calls]
    else:
        labels = [("run", expected.label)]
    return [item(key, label, predicted) for key, label in labels]
