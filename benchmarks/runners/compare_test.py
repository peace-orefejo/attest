from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import compare
from bench_check_metrics import Prices, check_metrics
from bench_compare import compare as compare_reports
from bench_compat import incompatibilities
from bench_grade import GradeSettings
from bench_report import BenchmarkReport
from bench_rows import ERROR, CaseRow, item


def _row(id_: str, expected: str, predicted: str) -> CaseRow:
    graded = item("run", expected, predicted)
    if predicted == ERROR:
        return CaseRow(
            id=id_,
            check="prompt_injection",
            category="c",
            source="synthetic",
            label_status="draft",
            status="errored",
            items=[graded],
            error="boom",
        )
    return CaseRow(
        id=id_,
        check="prompt_injection",
        category="c",
        source="synthetic",
        label_status="draft",
        items=[graded],
        correct=graded.correct,
        latency_s=0.1,
    )


def _report(predictions: list[str], **overrides: Any) -> BenchmarkReport:
    expected = ["payload", "payload", "compromised", "none", "none"]
    rows = [_row(f"c{i}", e, p) for i, (e, p) in enumerate(zip(expected, predictions, strict=True))]
    fields: dict[str, Any] = {
        "dataset_version": "v1",
        "attest_version": "0.0.0",
        "prompt_version": "p",
        "provider": "anthropic",
        "model": "m",
        "split": "dev",
        "timestamp": "2026-10-31T00:00:00+00:00",
        "settings": GradeSettings(),
        "all_cases_graded": all(row.graded for row in rows),
        "checks": {"prompt_injection": check_metrics("prompt_injection", rows, Prices())},
        "cases": rows,
    }
    fields.update(overrides)
    return BenchmarkReport(**fields)


GOOD = ["payload", "payload", "compromised", "none", "none"]
WORSE = ["payload", "none", "compromised", "none", "none"]  # one missed payload
ERRORED = ["payload", ERROR, "compromised", "none", "none"]


def test_recall_drop_is_a_regression_and_flips_are_listed() -> None:
    result = compare_reports(_report(GOOD), _report(WORSE), tolerance=0.02)
    assert result.regressed
    assert any("violation_detection.recall" in note for note in result.regressions)
    assert [(f.id, f.old_correct, f.new_correct) for f in result.flips] == [("c1", True, False)]
    recall = result.deltas["prompt_injection"]["violation_detection.recall"]
    assert recall.old == 1.0 and recall.new == pytest.approx(2 / 3)
    assert "coverage" in result.deltas["prompt_injection"]


def test_improvement_and_drops_within_tolerance_pass() -> None:
    assert not compare_reports(_report(WORSE), _report(GOOD), tolerance=0.0).regressed
    assert not compare_reports(_report(GOOD), _report(WORSE), tolerance=0.5).regressed


def test_like_for_like_reports_are_compatible() -> None:
    assert incompatibilities(_report(GOOD), _report(WORSE), min_coverage=0.95) == []


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"dataset_version": "v2"}, "dataset versions differ"),
        ({"split": "heldout"}, "splits differ"),
        ({"settings": GradeSettings(offline=True)}, "setting offline differs"),
        ({"settings": GradeSettings(answer_kind="plan")}, "setting answer_kind differs"),
        ({"settings": GradeSettings(appropriate=True)}, "setting appropriate differs"),
        ({"provider": "openai"}, "providers differ"),
        ({"model": "other"}, "models differ"),
        ({"all_cases_graded": False}, "cases that errored or didn't run"),
        ({"budget_exhausted": True, "stopped_reason": "spent"}, "ran out of budget: spent"),
    ],
)
def test_each_incompatibility_is_refused(overrides: dict[str, Any], reason: str) -> None:
    reasons = incompatibilities(_report(GOOD), _report(GOOD, **overrides), min_coverage=0.95)
    assert len(reasons) == 1 and reason in reasons[0], reasons


def test_low_coverage_is_refused() -> None:
    reasons = incompatibilities(_report(ERRORED), _report(GOOD), min_coverage=0.95)
    assert "the old report has cases that errored or didn't run" in reasons
    assert "prompt_injection coverage in the old report is 80.0%, below 95%" in reasons
    assert (
        incompatibilities(_report(ERRORED, all_cases_graded=True), _report(GOOD), min_coverage=0.8)
        == []
    )


def test_model_change_can_be_allowed_on_its_own() -> None:
    old, new = _report(GOOD), _report(GOOD, model="other")
    assert incompatibilities(old, new, min_coverage=0.95, allow_model_change=True) == []
    new_provider = _report(GOOD, model="other", provider="openai")
    reasons = incompatibilities(old, new_provider, min_coverage=0.95, allow_model_change=True)
    assert len(reasons) == 1 and "providers differ" in reasons[0]


def _write(tmp_path: Path, old: BenchmarkReport, new: BenchmarkReport) -> tuple[str, str]:
    old_path, new_path = tmp_path / "old.json", tmp_path / "new.json"
    old_path.write_text(old.model_dump_json())
    new_path.write_text(new.model_dump_json())
    return str(old_path), str(new_path)


def test_cli_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    old, new = _write(tmp_path, _report(GOOD), _report(WORSE))
    assert compare.main([old, new]) == 1
    assert "REGRESSION" in capsys.readouterr().out
    assert compare.main([new, old]) == 0
    assert compare.main([old, new, "--tolerance", "0.5"]) == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"dataset_version": "v2"},
        {"split": "heldout"},
        {"settings": GradeSettings(appropriate=True)},
        {"provider": "openai"},
        {"model": "other"},
        {"budget_exhausted": True},
    ],
)
def test_cli_refuses_incompatible_reports_without_deltas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], overrides: dict[str, Any]
) -> None:
    old, new = _write(tmp_path, _report(GOOD), _report(WORSE, **overrides))
    assert compare.main([old, new]) == compare.REFUSED
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Refusing to compare" in captured.err and "--allow-incompatible" in captured.err


def test_cli_refuses_low_coverage(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    old, new = _write(tmp_path, _report(GOOD), _report(ERRORED))
    assert compare.main([old, new]) == compare.REFUSED
    assert "coverage in the new report is 80.0%" in capsys.readouterr().err


def test_cli_override_compares_and_says_what_it_bypassed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old, new = _write(tmp_path, _report(GOOD), _report(WORSE, dataset_version="v2"))
    assert compare.main([old, new, "--allow-incompatible"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("!!! FORCED COMPARISON (--allow-incompatible)")
    assert "!!! - dataset versions differ" in out
    assert "violation_detection.recall" in out and "REGRESSION" in out


def test_cli_model_change_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    old, new = _write(tmp_path, _report(GOOD), _report(GOOD, model="other"))
    assert compare.main([old, new]) == compare.REFUSED
    assert compare.main([old, new, "--allow-model-change"]) == 0
    assert "FORCED" not in capsys.readouterr().out


def test_cli_json_records_bypassed_checks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old, new = _write(tmp_path, _report(GOOD), _report(GOOD, split="heldout"))
    assert compare.main([old, new, "--allow-incompatible", "--json"]) == 0
    assert '"bypassed": [\n    "splits differ (dev vs heldout)"' in capsys.readouterr().out


def test_cli_rejects_an_unreadable_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old, _ = _write(tmp_path, _report(GOOD), _report(GOOD))
    assert compare.main([old, str(tmp_path / "absent.json")]) == compare.REFUSED
    assert "can't read report" in capsys.readouterr().err
