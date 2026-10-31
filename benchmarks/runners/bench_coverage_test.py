from __future__ import annotations

import pytest

from attest import wilson_interval
from bench_check_metrics import Prices, check_metrics
from bench_grade import GradeSettings
from bench_report import BenchmarkReport, publishability
from bench_rows import ERROR, NOT_RUN, CaseRow, CaseStatus, item
from bench_summary import markdown_summary


def _row(
    id_: str, pairs: list[tuple[str, str]], status: CaseStatus = "graded", check: str = "x"
) -> CaseRow:
    items = [item(f"k{i}", e, p) for i, (e, p) in enumerate(pairs)]
    return CaseRow(
        id=id_,
        check=check,
        category="c",
        source="synthetic",
        label_status="confirmed",
        status=status,
        items=items,
        correct=all(i.correct for i in items) if status == "graded" else None,
        error=None if status == "graded" else "boom",
    )


def _reviewer_example() -> list[CaseRow]:
    """100 attempted runs, all labelled payload: 65 caught, 5 missed, 20 errored, 10 not run."""
    rows = [_row(f"ok{i}", [("payload", "payload")]) for i in range(65)]
    rows += [_row(f"miss{i}", [("payload", "none")]) for i in range(5)]
    rows += [_row(f"err{i}", [("payload", ERROR)], "errored") for i in range(20)]
    rows += [_row(f"skip{i}", [("payload", NOT_RUN)], "not_run") for i in range(10)]
    return rows


def test_errored_and_not_run_cases_lower_coverage_and_effective_accuracy() -> None:
    metrics = check_metrics("prompt_injection", _reviewer_example(), Prices())
    covered = metrics.coverage
    assert (covered.attempted, covered.graded, covered.errored, covered.not_run) == (
        100,
        70,
        20,
        10,
    )
    assert covered.coverage.value == pytest.approx(0.70)
    interval = wilson_interval(70, 100)
    assert (covered.coverage.low, covered.coverage.high) == (interval.low, interval.high)
    assert covered.operational_failure_rate.value == pytest.approx(0.20)
    assert (covered.operational_failure_rate.successes, covered.operational_failure_rate.n) == (
        20,
        100,
    )

    assert metrics.item_accuracy.value == pytest.approx(65 / 70)
    assert metrics.effective.item_accuracy.value == pytest.approx(65 / 100)
    assert metrics.case_accuracy.value == pytest.approx(65 / 70)
    assert metrics.effective.case_accuracy.value == pytest.approx(65 / 100)

    view = metrics.binary["violation_detection"]
    assert (view.tp, view.fn) == (65, 5)
    assert view.recall.value == pytest.approx(65 / 70)
    assert view.effective_recall.value == pytest.approx(65 / 100)
    assert view.effective_recall.n == 100
    assert sum(sum(row.values()) for row in metrics.confusion.matrix.values()) == 70


def test_effective_accuracy_counts_every_item_of_a_multi_item_case() -> None:
    rows = [
        _row("a", [("supported", "supported"), ("unsupported", "unsupported")]),
        _row("b", [("supported", "supported"), ("unverifiable", "supported")]),
        _row("c", [("supported", ERROR), ("unsupported", ERROR), ("supported", ERROR)], "errored"),
        _row("d", [("unsupported", NOT_RUN)], "not_run"),
    ]
    metrics = check_metrics("faithfulness", rows, Prices())
    assert (metrics.items, metrics.attempted_items) == (4, 8)
    assert metrics.item_accuracy.value == pytest.approx(3 / 4)
    assert metrics.effective.item_accuracy.value == pytest.approx(3 / 8)
    assert metrics.case_accuracy.value == pytest.approx(1 / 2)
    assert metrics.effective.case_accuracy.value == pytest.approx(1 / 4)
    assert metrics.coverage.coverage.value == pytest.approx(2 / 4)
    contradiction = metrics.binary["contradiction_detection"]
    assert contradiction.recall.value == 1.0
    assert contradiction.effective_recall.value == pytest.approx(1 / 3)
    sufficiency = metrics.binary["evidence_sufficiency"]
    assert sufficiency.recall.value == pytest.approx(1 / 2)
    assert sufficiency.effective_recall.value == pytest.approx(1 / 4)
    assert metrics.confusion.matrix["supported"].get(ERROR) is None


def _report(rows: list[CaseRow], *, offline: bool = False, drafts: bool = False) -> BenchmarkReport:
    if drafts:
        rows = [row.model_copy(update={"label_status": "draft"}) for row in rows]
    checks = {"prompt_injection": check_metrics("prompt_injection", rows, Prices())}
    settings = GradeSettings(offline=offline)
    blockers = publishability(checks, settings=settings, budget_exhausted=False, min_coverage=0.95)
    return BenchmarkReport(
        dataset_version="v" * 64,
        attest_version="0",
        prompt_version="p",
        provider="anthropic",
        model="m",
        split="dev",
        timestamp="t",
        settings=settings,
        all_cases_graded=all(row.graded for row in rows),
        publishable=not blockers,
        not_publishable_because=blockers,
        checks=checks,
        cases=rows,
    )


def test_low_coverage_blocks_publishing_and_is_warned() -> None:
    report = _report(_reviewer_example())
    assert not report.publishable
    assert report.not_publishable_because == [
        "prompt_injection coverage 70.0% is below the minimum 95%"
    ]
    summary = markdown_summary(report)
    assert "NOT PUBLISHABLE" in summary
    assert "| 70% 70/100 (" in summary
    assert "WARNING: prompt_injection coverage is 70%" in summary
    assert "item accuracy (effective)" in summary and "recall (effective)" in summary


def test_full_coverage_with_confirmed_labels_is_publishable() -> None:
    rows = [_row(f"ok{i}", [("payload", "payload")]) for i in range(20)]
    report = _report(rows)
    assert report.publishable and report.not_publishable_because == []
    assert "NOT PUBLISHABLE" not in markdown_summary(report)


def test_draft_labels_and_offline_runs_are_not_publishable() -> None:
    rows = [_row(f"ok{i}", [("payload", "payload")]) for i in range(20)]
    assert _report(rows, drafts=True).not_publishable_because == ["20 case(s) carry draft labels"]
    offline = _report(rows, offline=True)
    assert offline.not_publishable_because == ["offline run: no model was called"]


def test_threshold_is_inclusive() -> None:
    rows = [_row(f"ok{i}", [("payload", "payload")]) for i in range(19)]
    rows.append(_row("err", [("payload", ERROR)], "errored"))
    checks = {"prompt_injection": check_metrics("prompt_injection", rows, Prices())}
    settings = GradeSettings()
    assert (
        publishability(checks, settings=settings, budget_exhausted=False, min_coverage=0.95) == []
    )
    assert publishability(checks, settings=settings, budget_exhausted=True, min_coverage=0.95) == [
        "the call budget ran out"
    ]


def test_faithfulness_summary_names_both_views_and_the_fixed_extractor() -> None:
    rows = [_row("a", [("supported", "supported"), ("unsupported", "unsupported")])]
    checks = {"faithfulness": check_metrics("faithfulness", rows, Prices())}
    report = _report(rows).model_copy(update={"checks": checks})
    summary = markdown_summary(report)
    assert "| faithfulness | contradiction_detection | unsupported |" in summary
    assert "| faithfulness | evidence_sufficiency | unsupported + unverifiable |" in summary
    assert "fixed extractor" in summary and "**not** claim extraction" in summary
