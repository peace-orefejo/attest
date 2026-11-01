from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

import run
from attest import Attest, Budget
from bench_cases import CHECKS, SPLITS
from bench_check_metrics import Prices, check_metrics
from bench_grade import GRADERS, Graded, GradeSettings
from bench_load import Datasets, load_datasets
from bench_report import BenchmarkReport, publishability
from bench_run import run_benchmark
from bench_summary import markdown_summary


def test_offline_run_over_seed_dev_set(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "offline.json"
    assert run.main(["--offline", "--out", str(out)]) == 0

    report = BenchmarkReport.model_validate_json(out.read_text())
    assert report.split == "dev"
    assert report.model is None and report.settings.offline
    assert set(report.checks) == {"tool_use", "recovery", "prompt_injection"}
    assert set(report.skipped_checks) == {"faithfulness", "role_adherence"}
    assert report.all_cases_graded and not report.budget_exhausted
    assert report.format_version == 2
    assert not report.publishable
    assert "offline run: no model was called" in report.not_publishable_because
    assert any("draft labels" in reason for reason in report.not_publishable_because)
    assert all(row.status == "graded" for row in report.cases)
    assert all(m.coverage.coverage.value == 1.0 for m in report.checks.values())
    assert list(report.checks["prompt_injection"].binary) == ["violation_detection"]
    assert all(row.error is None and row.latency_s is not None for row in report.cases)
    assert all(row.usage.calls == 0 for row in report.cases)
    seeds = load_datasets()
    assert report.dataset_version == seeds.version
    assert report.checks["tool_use"].coverage.attempted == len(seeds.split("tool_use", "dev"))

    by_id = {row.id: row for row in report.cases}
    assert by_id["tool-prohibited-delete"].items[0].predicted == "disallowed_tool"
    assert by_id["rec-retried"].items[0].predicted == "retried"
    assert by_id["inj-payload-ignored"].items[0].predicted == "payload"

    summary = capsys.readouterr().out
    assert "| tool_use |" in summary
    assert "draft labels" in summary and "Offline run" in summary
    assert "NOT PUBLISHABLE" in summary and "| 100% 5/5 (" in summary
    assert "**not** claim extraction" in summary
    seed_rows = sum(row.origin == "attest-seed" for row in report.cases)
    assert seed_rows and f"attest-seed {seed_rows}" in summary.split("Cases by origin: ")[1]


def test_heldout_needs_explicit_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        run.main(["--offline", "--split", "heldout"])
    assert exc.value.code == 2
    assert "--heldout" in capsys.readouterr().err


def test_heldout_runs_with_flag(tmp_path: Path) -> None:
    out = tmp_path / "heldout.json"
    assert run.main(["--offline", "--split", "heldout", "--heldout", "--out", str(out)]) == 0
    assert BenchmarkReport.model_validate_json(out.read_text()).split == "heldout"


def test_validation_runs_without_the_heldout_flag(tmp_path: Path) -> None:
    calls = [{"tool_call": {"name": "pay", "output": "paid"}}]
    tool = {"calls": [{"step": 0, "verdict": "correct"}]}
    root = _write_tree(tmp_path / "datasets", {})
    case = _case("t-val", "tool_use", tool, calls)
    case["task_family"] = "fam-validation"
    (root / "tool_use" / "validation.jsonl").write_text(json.dumps(case) + "\n")
    out = tmp_path / "validation.json"
    argv = ["--offline", "--split", "validation", "--datasets", str(root), "--out", str(out)]
    assert run.main(argv) == 0

    report = BenchmarkReport.model_validate_json(out.read_text())
    assert report.split == "validation"
    assert report.checks["tool_use"].coverage.attempted == 1
    assert report.checks["tool_use"].coverage.graded == 1
    assert [row.status for row in report.cases] == ["graded"]

    public_out = tmp_path / "public-validation.json"
    assert run.main(["--offline", "--split", "validation", "--out", str(public_out)]) == 0
    public = BenchmarkReport.model_validate_json(public_out.read_text())
    assert public.split == "validation" and public.dataset_version == load_datasets().version


def test_an_empty_split_is_not_publishable(tmp_path: Path) -> None:
    empty = check_metrics("tool_use", [], Prices())
    blockers = publishability(
        {"tool_use": empty, "recovery": empty},
        split="validation",
        settings=GradeSettings(offline=False),
        budget_exhausted=False,
        min_coverage=0.95,
    )
    assert blockers == [
        "the run has no cases in validation",
        "no cases for tool_use in validation",
        "no cases for recovery in validation",
    ]

    report = run_benchmark(
        Attest(client=_FakeClient()),
        _datasets(tmp_path),
        checks=["faithfulness", "role_adherence"],
        split="validation",
        settings=GradeSettings(),
    )
    assert not report.publishable and not report.all_cases_graded
    assert report.not_publishable_because == [
        "the run has no cases in validation",
        "no cases for faithfulness in validation",
        "no cases for role_adherence in validation",
    ]
    summary = markdown_summary(report)
    assert "NOT PUBLISHABLE" in summary and "no cases for faithfulness in validation" in summary
    assert "n/a (0 cases)" in summary


def test_a_check_with_no_cases_blocks_an_otherwise_publishable_run(tmp_path: Path) -> None:
    datasets = _datasets(tmp_path)
    confirmed = {
        check: {
            split: [
                c.model_copy(update={"label_status": "confirmed", "annotators": ["a", "b"]})
                for c in cases
            ]
            for split, cases in by_split.items()
        }
        for check, by_split in datasets.cases.items()
    }
    report = run_benchmark(
        Attest(client=_FakeClient()),
        datasets.model_copy(update={"cases": confirmed}),
        checks=["role_adherence", "tool_use"],
        split="dev",
        settings=GradeSettings(),
    )
    assert report.not_publishable_because == ["no cases for tool_use in dev"]
    assert not report.publishable


def test_report_breaks_down_a_mixed_dataset_by_origin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = [{"tool_call": {"name": "pay", "output": "paid"}}]
    tool = {"calls": [{"step": 0, "verdict": "correct"}]}
    root = _write_tree(tmp_path / "datasets", {"tool_use": [_case("t1", "tool_use", tool, calls)]})
    external = _case("tau-t2", "tool_use", tool, calls)
    external.update(source="community", origin="tau-bench", task_family="tau-bench/retail")
    (root / "tool_use" / "dev-tau-bench.jsonl").write_text(json.dumps(external) + "\n")
    out = tmp_path / "mixed.json"
    assert run.main(["--offline", "--datasets", str(root), "--out", str(out)]) == 0

    report = BenchmarkReport.model_validate_json(out.read_text())
    assert sorted(row.origin or "" for row in report.cases) == ["attest-seed", "tau-bench"]
    per_origin = report.checks["tool_use"].per_origin
    assert sorted(per_origin) == ["attest-seed", "tau-bench"]
    assert per_origin["tau-bench"].coverage.attempted == 1
    summary = capsys.readouterr().out
    assert "Cases by origin: attest-seed 1, tau-bench 1." in summary
    assert "| tool_use | tau-bench | 100% 1/1 (" in summary


def test_offline_refuses_a_check_that_needs_a_model() -> None:
    with pytest.raises(SystemExit) as exc:
        run.main(["--offline", "--check", "faithfulness"])
    assert exc.value.code == 2


class _FakeClient:
    """Answers every judge question the same way, so model-backed paths run offline."""

    def __init__(self) -> None:
        self.calls = 0

    def create(self, *, response_model: type[BaseModel], **_: Any) -> BaseModel:
        self.calls += 1
        fields = response_model.model_fields
        if "verdicts" in fields:
            return response_model.model_validate(
                {
                    "verdicts": [
                        {"claim": 1, "verdict": "supported"},
                        {"claim": 2, "verdict": "unverifiable"},
                    ]
                }
            )
        if "outcome" in fields:
            return response_model.model_validate({"outcome": "failed"})
        if "unauthorized" in fields:
            return response_model.model_validate({"unauthorized": False})
        return response_model.model_validate({"verdict": "in_scope"})


def _write_tree(root: Path, cases: dict[str, list[dict[str, Any]]]) -> Path:
    for check in CHECKS:
        (root / check).mkdir(parents=True)
        for split in SPLITS:
            rows = cases.get(check, []) if split == "dev" else []
            (root / check / f"{split}.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in rows)
            )
    return root


def _case(id_: str, check: str, expected: dict[str, Any], steps: list[Any]) -> dict[str, Any]:
    return {
        "id": id_,
        "check": check,
        "category": "x",
        "source": "synthetic",
        "origin": "attest-seed",
        "task_family": "fam-dev",
        "label_status": "draft",
        "trajectory": {
            "task": "t",
            "system_prompt": "You answer billing questions.",
            "steps": steps,
            "final_answer": "Paid. Arrives Friday.",
        },
        "expected": expected,
    }


def _datasets(tmp_path: Path) -> Datasets:
    evidence = [{"tool_call": {"name": "pay", "output": "paid"}}]
    error = [{"tool_call": {"name": "pay", "output": "Error: declined"}}]
    claims = [
        {"text": "It was paid.", "label": "supported"},
        {"text": "It arrives Friday.", "label": "unverifiable"},
    ]
    return load_datasets(
        _write_tree(
            tmp_path,
            {
                "faithfulness": [_case("f1", "faithfulness", {"claims": claims}, evidence)],
                "recovery": [
                    _case(
                        "r1",
                        "recovery",
                        {"calls": [{"step": 0, "verdict": "correct", "recovery": "acknowledged"}]},
                        error,
                    )
                ],
                "role_adherence": [_case("o1", "role_adherence", {"label": "in_scope"}, [])],
            },
        )
    )


def test_model_backed_checks_with_a_fake_client(tmp_path: Path) -> None:
    client = _FakeClient()
    judge = Attest(client=client)
    report = run_benchmark(
        judge,
        _datasets(tmp_path),
        checks=["faithfulness", "recovery", "role_adherence"],
        split="dev",
        settings=GradeSettings(),
    )
    rows = {row.id: row for row in report.cases}
    faith = rows["f1"]
    assert [i.predicted for i in faith.items] == ["supported", "unverifiable"]
    assert faith.correct and faith.usage.calls == 1
    assert rows["r1"].items[0].predicted == "acknowledged"
    assert rows["o1"].items[0].predicted == "in_scope"
    assert report.checks["faithfulness"].claim_coverage is not None
    assert report.checks["faithfulness"].claim_coverage.value == 0.5
    assert client.calls == sum(row.usage.calls for row in report.cases)


def test_budget_stop_marks_the_rest_not_run(tmp_path: Path) -> None:
    judge = Attest(client=_FakeClient(), budget=Budget(max_calls=1))
    report = run_benchmark(
        judge,
        _datasets(tmp_path),
        checks=["faithfulness", "recovery", "role_adherence"],
        split="dev",
        settings=GradeSettings(),
    )
    assert report.budget_exhausted and not report.all_cases_graded
    assert not report.publishable
    assert "the call budget ran out" in report.not_publishable_because
    assert report.cases[0].correct is True
    assert all(row.error and row.error.startswith("not run") for row in report.cases[1:])
    assert all(row.status == "not_run" for row in report.cases[1:])
    recovery = next(row for row in report.cases if row.id == "r1")
    assert [(i.expected, i.predicted, i.correct) for i in recovery.items] == [
        ("acknowledged", "not_run", False)
    ]
    role = report.checks["role_adherence"]
    assert (role.coverage.attempted, role.coverage.graded, role.coverage.not_run) == (1, 0, 1)
    assert role.coverage.coverage.value == 0.0
    assert role.item_accuracy.value is None
    assert role.effective.item_accuracy.value == 0.0
    assert role.binary["violation_detection"].effective_recall.n == 0


def _explode(*_: object) -> Graded:
    raise RuntimeError("judge exploded")


def test_an_errored_case_keeps_its_items_and_counts_against_effective_accuracy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(GRADERS, "faithfulness", _explode)
    report = run_benchmark(
        Attest(client=_FakeClient()),
        _datasets(tmp_path),
        checks=["faithfulness", "role_adherence"],
        split="dev",
        settings=GradeSettings(),
    )
    row = next(row for row in report.cases if row.id == "f1")
    assert row.status == "errored" and row.correct is None
    assert row.error is not None and "judge exploded" in row.error
    assert [(i.expected, i.predicted) for i in row.items] == [
        ("supported", "error"),
        ("unverifiable", "error"),
    ]
    faith = report.checks["faithfulness"]
    assert (faith.coverage.errored, faith.coverage.graded) == (1, 0)
    assert faith.coverage.operational_failure_rate.value == 1.0
    assert faith.effective.item_accuracy.value == 0.0
    assert faith.binary["evidence_sufficiency"].effective_recall.value == 0.0
    assert not report.all_cases_graded and not report.budget_exhausted
    assert any("faithfulness coverage 0.0%" in r for r in report.not_publishable_because)


def test_external_datasets_folder_gives_a_private_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ATTEST_BENCH_ID_KEY", raising=False)
    root = tmp_path / "private"
    (root / "tool_use").mkdir(parents=True)
    public = load_datasets().split("tool_use", "dev")
    (root / "tool_use" / "dev.jsonl").write_text(
        "".join(case.model_dump_json() + "\n" for case in public)
    )
    out = tmp_path / "private.json"
    assert run.main(["--offline", "--datasets", str(root), "--out", str(out)]) == 0

    report = BenchmarkReport.model_validate_json(out.read_text())
    assert report.dataset_visibility == "private"
    assert report.checks["tool_use"].coverage.attempted == len(public)
    assert all(row.id.startswith("case-") for row in report.cases)
    assert not {case.id for case in public} & {row.id for row in report.cases}
    assert all(i.key.startswith("item-") for row in report.cases for i in row.items)
    assert report.case_id_key is None
    captured = capsys.readouterr()
    assert "Private dataset" in captured.out
    assert "ATTEST_BENCH_ID_KEY is not set" in captured.err

    monkeypatch.setenv("ATTEST_BENCH_ID_KEY", "secret")
    keyed_out = tmp_path / "keyed.json"
    assert run.main(["--offline", "--datasets", str(root), "--out", str(keyed_out)]) == 0
    keyed = BenchmarkReport.model_validate_json(keyed_out.read_text())
    assert keyed.case_id_key is not None and "secret" not in keyed_out.read_text()
    assert not {row.id for row in keyed.cases} & {row.id for row in report.cases}
    assert "is not set" not in capsys.readouterr().err
