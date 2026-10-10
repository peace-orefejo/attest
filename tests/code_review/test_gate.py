import pytest

from attest import CheckResult, Finding, Report, Severity
from attest.code_review.gate import DEFAULT_MODES, gate
from attest.code_review.models import OUTPUT_TYPES

SEVERITY = {"supported": Severity.PASS, "unsupported": Severity.FAIL, "unverifiable": Severity.WARN}


def faithfulness(*verdicts: str) -> Report:
    findings = [Finding(severity=SEVERITY[v], verdict=v, subject=f"claim {i}") for i, v in enumerate(verdicts)]
    passed = "unsupported" not in verdicts
    return Report(results=[CheckResult(check="faithfulness", passed=passed, findings=findings)])


def injection(*entries: tuple[str, str | None]) -> CheckResult:
    findings = []
    for verdict, file in entries:
        metadata = {} if file is None else {"file": file}
        severity = Severity.FAIL if verdict in {"payload", "compromised"} else Severity.WARN
        findings.append(Finding(severity=severity, verdict=verdict, subject=f"{verdict} in {file}", metadata=metadata))
    return CheckResult(check="code_injection", passed=not findings, findings=findings)


@pytest.mark.parametrize("output_type, expected", [
    ("issue", "lenient"),
    ("diff_summary", "strict"),
    ("group_summary", "strict"),
    ("canvas_answer", "strict"),
])
def test_default_mode_per_output_type(output_type, expected):
    assert gate(faithfulness("supported"), output_type).mode == expected


def test_every_output_type_has_a_default():
    assert set(DEFAULT_MODES) == set(OUTPUT_TYPES)


@pytest.mark.parametrize("output_type", OUTPUT_TYPES)
def test_all_supported_keeps_with_no_reasons(output_type):
    decision = gate(faithfulness("supported", "supported"), output_type)
    assert decision.keep
    assert decision.reasons == []


@pytest.mark.parametrize("mode", ["lenient", "strict"])
def test_unsupported_drops_in_every_mode(mode):
    decision = gate(faithfulness("supported", "unsupported"), "issue", mode=mode)
    assert not decision.keep
    assert [f.verdict for f in decision.reasons] == ["unsupported"]


def test_lenient_keeps_unverifiable():
    decision = gate(faithfulness("supported", "unverifiable"), "issue", mode="lenient")
    assert decision.keep
    assert decision.reasons == []


def test_strict_drops_unverifiable():
    decision = gate(faithfulness("supported", "unverifiable"), "issue", mode="strict")
    assert not decision.keep
    assert [f.verdict for f in decision.reasons] == ["unverifiable"]


def test_strict_reasons_list_every_offending_finding_in_order():
    decision = gate(faithfulness("unverifiable", "supported", "unsupported"), "diff_summary")
    assert [f.subject for f in decision.reasons] == ["claim 0", "claim 2"]


@pytest.mark.parametrize("output_type", ["diff_summary", "group_summary", "canvas_answer"])
def test_strict_default_drops_unverifiable_summaries_and_answers(output_type):
    assert not gate(faithfulness("unverifiable"), output_type).keep


def test_issue_default_keeps_unverifiable():
    assert gate(faithfulness("unverifiable"), "issue").keep


def test_explicit_mode_overrides_default():
    report = faithfulness("unverifiable")
    assert gate(report, "issue", mode="strict").mode == "strict"
    assert not gate(report, "issue", mode="strict").keep
    assert gate(report, "canvas_answer", mode="lenient").mode == "lenient"
    assert gate(report, "canvas_answer", mode="lenient").keep


@pytest.mark.parametrize("output_type", OUTPUT_TYPES)
def test_missing_faithfulness_result_keeps(output_type):
    decision = gate(Report(results=[]), output_type)
    assert decision.keep
    assert decision.reasons == []


def test_other_checks_are_ignored():
    other = CheckResult(check="tool_use", passed=False,
                        findings=[Finding(severity=Severity.FAIL, verdict="unsupported")])
    assert gate(Report(results=[other]), "canvas_answer").keep


@pytest.mark.parametrize("verdict", ["payload", "compromised"])
@pytest.mark.parametrize("mode", ["lenient", "strict"])
def test_blocking_injection_drops_whatever_the_mode(verdict, mode):
    decision = gate(faithfulness("supported"), "issue", mode=mode, injection=injection((verdict, "app/a.py")))
    assert not decision.keep
    assert [f.verdict for f in decision.reasons] == [verdict]


def test_suspicious_keeps_and_adds_a_note():
    decision = gate(faithfulness("supported"), "issue", injection=injection(("suspicious", "app/a.py")))
    assert decision.keep
    assert [f.verdict for f in decision.reasons] == ["suspicious"]


def test_clean_adds_nothing():
    decision = gate(faithfulness("supported"), "issue", injection=injection(("clean", "app/a.py")))
    assert decision.keep
    assert decision.reasons == []


def test_unknown_injection_verdict_is_ignored():
    decision = gate(faithfulness("supported"), "issue", injection=injection(("weird", "app/a.py")))
    assert decision.keep
    assert decision.reasons == []


def test_suspicious_does_not_rescue_a_faithfulness_drop():
    decision = gate(faithfulness("unsupported"), "issue", injection=injection(("suspicious", "app/a.py")))
    assert not decision.keep
    assert [f.verdict for f in decision.reasons] == ["unsupported", "suspicious"]


def test_reasons_combine_faithfulness_and_injection():
    decision = gate(faithfulness("unverifiable"), "diff_summary",
                    injection=injection(("payload", "app/a.py"), ("suspicious", "app/b.py")))
    assert not decision.keep
    assert [f.verdict for f in decision.reasons] == ["unverifiable", "payload", "suspicious"]


def test_payload_outside_paths_is_ignored():
    decision = gate(faithfulness("supported"), "issue",
                    injection=injection(("payload", "app/other.py")), paths=["app/a.py"])
    assert decision.keep
    assert decision.reasons == []


def test_payload_inside_paths_drops():
    decision = gate(faithfulness("supported"), "issue",
                    injection=injection(("payload", "app/other.py"), ("compromised", "app/a.py")),
                    paths=["app/a.py"])
    assert not decision.keep
    assert [f.metadata["file"] for f in decision.reasons] == ["app/a.py"]


def test_suspicious_outside_paths_adds_no_note():
    decision = gate(faithfulness("supported"), "issue",
                    injection=injection(("suspicious", "app/other.py")), paths=["app/a.py"])
    assert decision.reasons == []


def test_no_paths_means_every_file_applies():
    decision = gate(faithfulness("supported"), "group_summary", injection=injection(("payload", "any/file.py")))
    assert not decision.keep


def test_empty_paths_matches_no_file():
    decision = gate(faithfulness("supported"), "issue", injection=injection(("payload", "app/a.py")), paths=[])
    assert decision.keep


def test_injection_finding_without_file_applies_to_any_paths():
    decision = gate(faithfulness("supported"), "issue", injection=injection(("payload", None)), paths=["app/a.py"])
    assert not decision.keep


def test_wrong_injection_check_name_is_rejected():
    wrong = CheckResult(check="injection", passed=True)
    with pytest.raises(ValueError, match="code_injection"):
        gate(faithfulness("supported"), "issue", injection=wrong)


def test_unknown_output_type_is_rejected():
    with pytest.raises(ValueError, match="output type"):
        gate(faithfulness("supported"), "commit_message")


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="gate mode"):
        gate(faithfulness("supported"), "issue", mode="paranoid")


def test_gate_does_not_mutate_the_report():
    report = faithfulness("unsupported")
    before = report.model_dump()
    gate(report, "issue", injection=injection(("payload", "app/a.py")))
    assert report.model_dump() == before


def test_public_import_path():
    from attest.code_review.gate import GateDecision
    assert isinstance(gate(faithfulness("supported"), "issue"), GateDecision)
