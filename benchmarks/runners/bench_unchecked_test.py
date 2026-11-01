"""A check whose model call failed is an errored case, never a graded label."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from attest import Attest, CheckResult, Finding, Severity
from bench_cases import CHECKS, SPLITS, CheckName
from bench_grade import GradeSettings
from bench_load import load_datasets
from bench_run import run_benchmark
from bench_unchecked import UncheckedResult, raise_if_unchecked


class _FailingClient:
    """Every judge call fails, as it does with a missing or rejected API key."""

    def __init__(self) -> None:
        self.calls = 0

    def create(self, *, response_model: type[BaseModel], **_: Any) -> BaseModel:
        self.calls += 1
        raise RuntimeError("authentication failed: no API key")


def _case(id_: str, check: str, expected: dict[str, Any], output: str) -> dict[str, Any]:
    return {
        "id": id_,
        "check": check,
        "category": "x",
        "source": "synthetic",
        "origin": "attest-seed",
        "task_family": "fam-validation",
        "label_status": "draft",
        "trajectory": {
            "task": "Pay the invoice.",
            "system_prompt": "You pay invoices.",
            "steps": [{"tool_call": {"name": "pay", "output": output}}],
            "final_answer": "Paid.",
        },
        "expected": expected,
    }


CASES: dict[str, dict[str, Any]] = {
    "prompt_injection": _case("inj", "prompt_injection", {"label": "none"}, "paid"),
    "role_adherence": _case("role", "role_adherence", {"label": "in_scope"}, "paid"),
    "faithfulness": _case(
        "faith", "faithfulness", {"claims": [{"text": "Paid.", "label": "unverifiable"}]}, "ok"
    ),
    "tool_use": _case("tool", "tool_use", {"calls": [{"step": 0, "verdict": "correct"}]}, "paid"),
    "recovery": _case(
        "rec",
        "recovery",
        {"calls": [{"step": 0, "verdict": "error_silent", "recovery": "silent"}]},
        "Error: declined",
    ),
}


def _run(tmp_path: Path, check: CheckName, settings: GradeSettings) -> Any:
    for name in CHECKS:
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
        for split in SPLITS:
            rows = [CASES[name]] if split == "validation" else []
            (tmp_path / name / f"{split}.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows)
            )
    return run_benchmark(
        Attest(client=_FailingClient()),
        load_datasets(tmp_path, public=False),
        checks=[check],
        split="validation",
        settings=settings,
    )


@pytest.mark.parametrize(
    ("check", "settings"),
    [
        ("prompt_injection", GradeSettings()),
        ("role_adherence", GradeSettings()),
        ("faithfulness", GradeSettings()),
        ("tool_use", GradeSettings(appropriate=True)),
        ("recovery", GradeSettings()),
    ],
)
def test_a_failed_model_call_is_an_errored_case_not_a_clean_label(
    tmp_path: Path, check: CheckName, settings: GradeSettings
) -> None:
    report = _run(tmp_path, check, settings)
    [row] = report.cases
    assert row.status == "errored" and row.correct is None
    assert row.error is not None and "UncheckedResult" in row.error
    assert all(item.predicted == "error" for item in row.items)
    metrics = report.checks[check]
    assert (metrics.coverage.graded, metrics.coverage.errored) == (0, 1)
    assert metrics.effective.item_accuracy.value == 0.0
    assert not report.all_cases_graded and not report.publishable


def test_an_offline_unchecked_recovery_is_still_the_documented_prediction(
    tmp_path: Path,
) -> None:
    report = _run(tmp_path, "recovery", GradeSettings(offline=True))
    [row] = report.cases
    assert row.status == "graded" and row.items[0].predicted == "unchecked"


def _result(**finding: Any) -> CheckResult:
    fields: dict[str, Any] = {"severity": Severity.WARN, "verdict": "none", "subject": "s"}
    fields.update(finding)
    return CheckResult(
        check="prompt_injection", passed=True, summary="", findings=[Finding(**fields)]
    )


def test_raise_if_unchecked_reads_every_kind_of_unchecked_finding() -> None:
    with pytest.raises(UncheckedResult, match="'deep-analysis' unchecked: it failed"):
        raise_if_unchecked(
            _result(verdict="unchecked", subject="deep-analysis", reason="it failed")
        )
    with pytest.raises(UncheckedResult, match="step 2"):
        raise_if_unchecked(_result(verdict="unverifiable", step=2, metadata={"checked": False}))
    recovery = _result(verdict="error_silent", metadata={"recovery": "unchecked"})
    with pytest.raises(UncheckedResult):
        raise_if_unchecked(recovery)
    raise_if_unchecked(recovery, answer_checked=False)
    raise_if_unchecked(_result(verdict="unverifiable", metadata={"checked": True}))
    raise_if_unchecked(None)
