from __future__ import annotations

from pathlib import Path

import pytest

import compare
from bench_check_metrics import Prices, check_metrics
from bench_compare import compare as compare_reports
from bench_grade import GradeSettings
from bench_report import BenchmarkReport
from bench_rows import CaseRow, item


def _row(id_: str, expected: str, predicted: str) -> CaseRow:
    graded = item("run", expected, predicted)
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


def _report(predictions: list[str], dataset_version: str = "v1") -> BenchmarkReport:
    expected = ["payload", "payload", "compromised", "none", "none"]
    rows = [_row(f"c{i}", e, p) for i, (e, p) in enumerate(zip(expected, predictions, strict=True))]
    return BenchmarkReport(
        dataset_version=dataset_version,
        attest_version="0.0.0",
        prompt_version="p",
        provider="anthropic",
        model="m",
        split="dev",
        timestamp="2026-10-31T00:00:00+00:00",
        settings=GradeSettings(),
        checks={"prompt_injection": check_metrics("prompt_injection", rows, Prices())},
        cases=rows,
    )


GOOD = ["payload", "payload", "compromised", "none", "none"]
WORSE = ["payload", "none", "compromised", "none", "none"]  # one missed payload


def test_recall_drop_is_a_regression_and_flips_are_listed() -> None:
    result = compare_reports(_report(GOOD), _report(WORSE), tolerance=0.02)
    assert result.regressed
    assert any("recall" in note for note in result.regressions)
    assert [(f.id, f.old_correct, f.new_correct) for f in result.flips] == [("c1", True, False)]
    recall = result.deltas["prompt_injection"]["recall"]
    assert recall.old == 1.0 and recall.new == pytest.approx(2 / 3)


def test_improvement_and_drops_within_tolerance_pass() -> None:
    assert not compare_reports(_report(WORSE), _report(GOOD), tolerance=0.0).regressed
    assert not compare_reports(_report(GOOD), _report(WORSE), tolerance=0.5).regressed


def test_dataset_change_is_warned() -> None:
    result = compare_reports(_report(GOOD), _report(GOOD, "v2"), tolerance=0.0)
    assert any("Dataset versions differ" in note for note in result.warnings)


def test_cli_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    old.write_text(_report(GOOD).model_dump_json())
    new.write_text(_report(WORSE).model_dump_json())
    assert compare.main([str(old), str(new)]) == 1
    assert "REGRESSION" in capsys.readouterr().out
    assert compare.main([str(new), str(old)]) == 0
    assert compare.main([str(old), str(new), "--tolerance", "0.5"]) == 0
