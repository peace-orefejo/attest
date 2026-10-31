"""Finding dispositions and the report verdict — offline, with hand-built findings."""

import pytest
from pydantic import ValidationError

from attest import Attest, EvaluationPolicy, EvaluationRule, ToolUsePolicy, VerdictPolicy
from attest.results import CheckResult, Finding, Report, Severity
from attest.scoring.dispositions import apply_verdict_policy, disposition_for
from attest.scoring.report import evaluate
from attest.trajectory import Step, ToolCall, Trajectory

PASS, WARN, FAIL = Severity.PASS, Severity.WARN, Severity.FAIL


def _finding(verdict: str, severity: Severity = FAIL, **metadata) -> Finding:
    return Finding(severity=severity, verdict=verdict, subject="s", metadata=metadata)


def _report(*results: tuple[str, list[Finding], float | None]) -> Report:
    return Report(
        results=[
            CheckResult(
                check=check,
                passed=all(f.severity is not FAIL for f in findings),
                score=score,
                findings=findings,
            )
            for check, findings, score in results
        ]
    )


@pytest.mark.parametrize(
    ("check", "verdict", "severity", "expected"),
    [
        ("faithfulness", "supported", PASS, "pass"),
        ("faithfulness", "unverifiable", WARN, "pass"),
        ("faithfulness", "unsupported", FAIL, "block"),
        ("tool_use", "correct", PASS, "pass"),
        ("tool_use", "disallowed_tool", FAIL, "block"),
        ("tool_use", "error_silent", FAIL, "review"),
        ("tool_use", "error_claimed_success", FAIL, "block"),
        ("tool_use", "inappropriate", FAIL, "review"),
        ("tool_use", "unnecessary_call", WARN, "review"),
        ("tool_use", "invalid_arguments", FAIL, "review"),
        ("tool_use", "incorrect", FAIL, "block"),
        ("injection", "compromised", FAIL, "block"),
        ("injection", "suspicious", WARN, "pass"),
        ("injection", "possible_injection", WARN, "pass"),
        ("injection", "unscanned_content", WARN, "pass"),
        ("injection", "clean", PASS, "pass"),
        ("role", "out_of_scope_complied", FAIL, "block"),
        ("role", "in_scope", PASS, "pass"),
        ("role", "unchecked", WARN, "review"),
        ("tool_use", "unchecked", WARN, "review"),
        ("injection", "unchecked", WARN, "review"),
        ("policy", "unchecked", WARN, "review"),
        ("policy", "violated", FAIL, "block"),
        ("policy", "violated", WARN, "review"),
        ("policy", "incomplete", WARN, "review"),
        ("policy", "compliant", PASS, "pass"),
        ("custom", "anything", FAIL, "block"),
        ("custom", "anything", WARN, "pass"),
        ("custom", "anything", PASS, "pass"),
    ],
)
def test_default_dispositions(check, verdict, severity, expected):
    finding = _finding(verdict, severity)
    assert disposition_for(check, finding, VerdictPolicy()) == expected


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"allowed": False, "error_handled": None, "appropriate": None}, "block"),
        ({"allowed": True, "error_handled": False, "appropriate": None}, "block"),
        ({"allowed": True, "error_handled": None, "appropriate": False}, "review"),
    ],
)
def test_legacy_incorrect_reads_which_rule_failed(metadata, expected):
    finding = _finding("incorrect", FAIL, **metadata)
    assert disposition_for("tool_use", finding, VerdictPolicy()) == expected


def test_strictest_disposition_wins():
    report = apply_verdict_policy(
        _report(
            ("faithfulness", [_finding("supported", PASS)] * 9, 0.9),
            ("tool_use", [_finding("error_silent")], 0.0),
            ("injection", [_finding("compromised")], None),
        )
    )
    assert report.verdict == "block"
    assert [(b.check, b.verdict) for b in report.blocking] == [("injection", "compromised")]
    assert report.scores == {"faithfulness": 0.9, "tool_use": 0.0, "injection": None}


def test_review_without_block():
    report = apply_verdict_policy(_report(("tool_use", [_finding("error_silent")], 0.0)))
    assert report.verdict == "review"
    assert report.blocking == []
    assert report.passed is False


def test_min_score_turns_passing_findings_into_review():
    findings = [_finding("supported", PASS), _finding("unverifiable", WARN)]
    raw = _report(("faithfulness", findings, 0.5))
    assert apply_verdict_policy(raw).verdict == "pass"
    floored = apply_verdict_policy(raw, VerdictPolicy(min_score={"faithfulness": 0.9}))
    assert floored.verdict == "review"
    assert {f.disposition for f in floored.results[0].findings} == {"review"}
    assert floored.passed is True


def test_min_score_ignores_unscored_and_passing_checks():
    policy = VerdictPolicy(min_score={"faithfulness": 0.5, "injection": 0.9})
    report = apply_verdict_policy(
        _report(
            ("faithfulness", [_finding("supported", PASS)], 0.5),
            ("injection", [_finding("clean", PASS)], None),
        ),
        policy,
    )
    assert report.verdict == "pass"


def test_custom_policy_overrides_defaults():
    policy = VerdictPolicy(
        tool_use=ToolUsePolicy(on_disallowed_tool="review", on_unhandled_error="block"),
        on_injection_warning="review",
    )
    assert disposition_for("tool_use", _finding("disallowed_tool"), policy) == "review"
    assert disposition_for("tool_use", _finding("error_silent"), policy) == "block"
    assert disposition_for("injection", _finding("suspicious", WARN), policy) == "review"
    assert disposition_for("injection", _finding("compromised"), policy) == "block"


def test_policy_is_frozen_and_strict():
    with pytest.raises(ValidationError):
        VerdictPolicy(on_injection_warning="ignore")
    with pytest.raises(ValidationError):
        VerdictPolicy(min_score={"faithfulness": 1.5})
    with pytest.raises(ValidationError):
        ToolUsePolicy(on_typo="block")
    with pytest.raises(ValidationError):
        VerdictPolicy().on_injection_warning = "block"


def test_unassigned_findings_fall_back_on_severity():
    report = _report(("custom", [_finding("x", FAIL), _finding("y", WARN)], None))
    assert report.verdict == "block"
    assert [b.verdict for b in report.blocking] == ["x"]


def _traj() -> Trajectory:
    return Trajectory(
        task="do it",
        allowed_tools=["search"],
        steps=[Step(tool_call=ToolCall(name="search", arguments={}, output="found it"))],
        final_answer="A",
    )


def _supported(claims, _evidence):
    return [Finding(severity=PASS, verdict="supported", subject=c) for c in claims]


def _unsupported(claims, _evidence):
    return [Finding(severity=FAIL, verdict="unsupported", subject=c) for c in claims]


def test_evaluate_fills_dispositions_and_verdict():
    report = evaluate(_traj(), extract=lambda _a: ["claim"], verify=_unsupported)
    assert all(f.disposition is not None for r in report.results for f in r.findings)
    assert report.verdict == "block"
    assert report.blocking[0].check == "faithfulness"
    assert report.passed is False
    dumped = report.model_dump()
    assert {"verdict", "blocking", "scores", "passed", "overall_score"} <= dumped.keys()


def test_attest_threads_verdict_policy():
    policy = VerdictPolicy(min_score={"tool_use": 1.0, "faithfulness": 1.0})
    report = Attest(verdict_policy=policy).evaluate(
        _traj(), extract=lambda _a: ["claim"], verify=_supported
    )
    assert report.verdict == "pass"
    assert report.passed is True


def test_attest_disposes_project_policy_findings():
    rules = EvaluationPolicy(
        name="support",
        rules=[
            EvaluationRule(
                id="no-guarantees",
                description="Do not guarantee outcomes.",
                kind="forbidden_text",
                values=["guaranteed"],
                severity="warn",
            )
        ],
    )
    traj = _traj().model_copy(update={"final_answer": "It is guaranteed."})
    report = Attest(policy=rules).evaluate(traj, checks=["tool_use"])
    assert report.by("policy").findings[0].disposition == "review"
    assert report.verdict == "review"


def test_inconclusive_faithfulness_is_review_not_pass():
    report = _report(("faithfulness", [_finding("unverifiable", WARN)], None))
    disposed = apply_verdict_policy(report)
    assert disposed.verdict == "review"
    assert disposed.results[0].findings[0].disposition == "review"


def test_one_checked_claim_keeps_other_unverifiable_claims_passing():
    report = _report(
        (
            "faithfulness",
            [_finding("supported", PASS), _finding("unverifiable", WARN)],
            1.0,
        )
    )
    assert apply_verdict_policy(report).verdict == "pass"


def test_inconclusive_faithfulness_disposition_is_configurable():
    report = _report(("faithfulness", [_finding("unverifiable", WARN)], None))
    policy = VerdictPolicy(on_inconclusive_faithfulness="block")
    assert apply_verdict_policy(report, policy).verdict == "block"


def test_an_answer_with_no_claims_is_not_inconclusive():
    report = _report(("faithfulness", [], 1.0))
    assert apply_verdict_policy(report).verdict == "pass"


def test_on_invalid_arguments_is_deprecated():
    with pytest.warns(DeprecationWarning, match="no effect"):
        ToolUsePolicy(on_invalid_arguments="block")


def test_the_default_tool_use_policy_raises_no_warning(recwarn):
    ToolUsePolicy()
    VerdictPolicy()
    assert not [w for w in recwarn if issubclass(w.category, DeprecationWarning)]


def test_the_deprecated_option_keeps_its_old_default():
    assert ToolUsePolicy().on_invalid_arguments == "review"


def test_an_empty_custom_verifier_gives_a_review_verdict():
    from attest import Attest

    traj = Trajectory(
        task="q",
        steps=[Step(tool_call=ToolCall(name="search", arguments={}, output="data"))],
        final_answer="a",
    )
    report = Attest(key="x").evaluate(
        traj,
        checks=("faithfulness",),
        extract=lambda a: ["c1", "c2"],
        verify=lambda claims, evidence: [],
    )
    assert report.verdict == "review"
    assert report.results[0].score is None


def _faithfulness(checked: int, total: int) -> Report:
    findings = [_finding("supported", PASS)] * checked + [_finding("unverifiable", WARN)] * (
        total - checked
    )
    result = CheckResult(
        check="faithfulness",
        passed=True,
        score=1.0 if checked else None,
        findings=findings,
        metadata={"claims_checked": checked, "claims_total": total},
    )
    return Report(results=[result])


def test_min_claim_coverage_is_off_by_default():
    assert apply_verdict_policy(_faithfulness(1, 40)).verdict == "pass"


def test_low_claim_coverage_goes_to_review():
    policy = VerdictPolicy(min_claim_coverage=0.8)
    assert apply_verdict_policy(_faithfulness(1, 40), policy).verdict == "review"


def test_enough_claim_coverage_passes():
    policy = VerdictPolicy(min_claim_coverage=0.8)
    assert apply_verdict_policy(_faithfulness(8, 10), policy).verdict == "pass"


def test_claim_coverage_doesnt_soften_a_block():
    report = _faithfulness(1, 10)
    report.results[0].findings.append(_finding("unsupported", FAIL))
    policy = VerdictPolicy(min_claim_coverage=0.8)
    assert apply_verdict_policy(report, policy).verdict == "block"


def test_claim_coverage_ignores_an_answer_with_no_claims():
    policy = VerdictPolicy(min_claim_coverage=0.8)
    assert apply_verdict_policy(_faithfulness(0, 0), policy).verdict == "pass"


def test_min_claim_coverage_must_be_a_share():
    with pytest.raises(ValidationError):
        VerdictPolicy(min_claim_coverage=1.5)


def test_report_exposes_claim_coverage():
    assert _faithfulness(1, 40).claim_coverage == 1 / 40
    assert _faithfulness(0, 0).claim_coverage is None
    assert Report(results=[]).claim_coverage is None


def test_an_unchecked_claim_is_review_even_beside_supported_ones():
    unchecked = _finding("unverifiable", WARN, checked=False)
    report = apply_verdict_policy(
        _report(("faithfulness", [_finding("supported", PASS), unchecked], 1.0))
    )
    assert [f.disposition for f in report.results[0].findings] == ["pass", "review"]
    assert report.verdict == "review"


def test_an_unchecked_claim_follows_on_inconclusive_faithfulness():
    unchecked = _finding("unverifiable", WARN, checked=False)
    policy = VerdictPolicy(on_inconclusive_faithfulness="block")
    report = apply_verdict_policy(
        _report(("faithfulness", [_finding("supported", PASS), unchecked], 1.0)), policy
    )
    assert report.verdict == "block"
