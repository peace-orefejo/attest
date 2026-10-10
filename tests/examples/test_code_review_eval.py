import importlib
import json
import sys
from pathlib import Path

import pytest

from attest import CheckResult, Finding, Report, Severity

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
sys.path.insert(0, str(EXAMPLES))

harness = importlib.import_module("code_review_eval")
scoring = importlib.import_module("code_review_eval_report")

SEVERITY = {"supported": Severity.PASS, "unsupported": Severity.FAIL, "unverifiable": Severity.WARN}


def report(*verdicts: str) -> Report:
    findings = [Finding(severity=SEVERITY[v], verdict=v, subject=f"claim {i}") for i, v in enumerate(verdicts)]
    return Report(results=[CheckResult(check="faithfulness", passed="unsupported" not in verdicts, findings=findings)])


def case(kind: str, expect: str, case_id: str = "c") -> dict:
    return {"id": case_id, "kind": kind, "expect": expect}


class FakeJudge:
    def __init__(self, by_kind: dict[str, dict[str, Report]]):
        self.by_kind = by_kind
        self.calls: list[tuple[str, str, tuple]] = []

    def evaluate(self, traj, *, checks, answer_kind):
        self.calls.append((traj.final_answer, answer_kind, tuple(checks)))
        return self.by_kind[answer_kind][traj.final_answer]


def test_score_case_uses_the_case_kind_as_output_type():
    row = scoring.score_case(case("issue", "pass"), report("supported", "unverifiable"))
    assert row["lenient_drop"] is False and row["lenient_ok"] is True
    assert row["strict_drop"] is True and row["strict_ok"] is False
    assert row["strict_reasons"] == ["claim 1"]
    assert row["verdicts"] == ["supported", "unverifiable"]


def test_score_case_unsupported_is_caught_in_both_modes():
    row = scoring.score_case(case("diff_summary", "flag"), report("unsupported"))
    assert row["lenient_ok"] and row["strict_ok"]


def test_score_case_without_faithfulness_keeps():
    row = scoring.score_case(case("canvas_answer", "flag"), Report(results=[]))
    assert row["verdicts"] == []
    assert not row["lenient_drop"] and not row["strict_drop"]


def test_summarize_counts_caught_and_blocked_with_wilson_accuracy():
    rows = [
        scoring.score_case(case("issue", "flag", "a"), report("unsupported")),
        scoring.score_case(case("issue", "flag", "b"), report("unverifiable")),
        scoring.score_case(case("issue", "pass", "c"), report("supported")),
        scoring.score_case(case("diff_summary", "pass", "d"), report("unverifiable")),
    ]
    lenient = scoring.summarize(rows, "lenient")
    strict = scoring.summarize(rows, "strict")
    assert lenient["issue"]["bad_outputs_caught"] == "1/2"
    assert strict["issue"]["bad_outputs_caught"] == "2/2"
    assert lenient["all"]["good_outputs_blocked"] == "0/2"
    assert strict["all"]["good_outputs_blocked"] == "1/2"
    assert lenient["all"]["accuracy"].startswith("75% (95% CI")
    assert strict["all"]["accuracy"].endswith("n=4)")
    assert set(scoring.summarize_modes(rows)) == {"lenient", "strict"}


def test_load_cases_reads_the_fixture_and_filters_by_kind():
    all_cases = scoring.load_cases(harness.DEFAULT_CASES)
    issues = scoring.load_cases(harness.DEFAULT_CASES, "issue")
    assert len(all_cases) > len(issues) > 0
    assert all(c["kind"] == "issue" for c in issues)
    assert all(c["trajectory"].final_answer for c in all_cases)


def test_run_cases_and_compare_formatting_offline():
    cases = scoring.load_cases(harness.DEFAULT_CASES, "issue")[:2]
    answers = [c["trajectory"].final_answer for c in cases]
    judge = FakeJudge({
        "factual": {answers[0]: report("unverifiable"), answers[1]: report("supported")},
        "code": {answers[0]: report("supported"), answers[1]: report("unsupported")},
    })
    results = {kind: harness.run_cases(judge, cases, kind) for kind in harness.COMPARE_KINDS}
    assert [c[1] for c in judge.calls] == ["factual", "factual", "code", "code"]
    assert all(c[2] == ("faithfulness",) for c in judge.calls)
    lines = scoring.format_compare(results)
    assert "factual L/S" in lines[0] and "code L/S" in lines[0]
    assert any(cases[0]["id"] in line for line in lines)
    assert any(line.strip().startswith("issue") and "factual" in line for line in lines)
    assert any(line.strip().startswith("code") and "caught" in line for line in lines)


def test_main_dry_run_makes_no_model_calls(monkeypatch, capsys):
    monkeypatch.setattr(harness, "Attest", lambda **_: pytest.fail("dry run built a judge"))
    harness.main(["--dry-run", "--compare"])
    out = capsys.readouterr().out
    assert "answer kinds: factual, code" in out
    assert "issue" in out


def test_main_defaults_to_code_answer_kind(capsys):
    harness.main(["--dry-run"])
    assert "answer kinds: code" in capsys.readouterr().out
    assert harness.build_parser().parse_args([]).answer_kind == "code"


def test_answer_kind_choices():
    parser = harness.build_parser()
    for kind in ("factual", "plan", "code", "auto"):
        assert parser.parse_args(["--answer-kind", kind]).answer_kind == kind
    with pytest.raises(SystemExit):
        parser.parse_args(["--answer-kind", "poetry"])


def test_main_json_with_fake_judge(monkeypatch, capsys):
    cases = scoring.load_cases(harness.DEFAULT_CASES, "canvas_answer")
    fake = FakeJudge({"factual": {c["trajectory"].final_answer: report("supported") for c in cases}})
    monkeypatch.setattr(harness, "Attest", lambda **_: fake)
    harness.main(["--kind", "canvas_answer", "--answer-kind", "factual", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"factual"}
    assert len(payload["factual"]["cases"]) == len(cases)
    assert payload["factual"]["summary"]["lenient"]["all"]["good_outputs_blocked"].startswith("0/")


def test_main_single_text_output_with_fake_judge(monkeypatch, capsys):
    cases = scoring.load_cases(harness.DEFAULT_CASES, "group_summary")
    fake = FakeJudge({"code": {c["trajectory"].final_answer: report("unverifiable") for c in cases}})
    monkeypatch.setattr(harness, "Attest", lambda **_: fake)
    harness.main(["--kind", "group_summary"])
    out = capsys.readouterr().out
    assert "\nlenient" in out and "\nstrict" in out
    assert all(c["id"] in out for c in cases)
