"""Report scoring and the verdict of a report built without `evaluate()`."""

from attest.disposition_rules import DEFAULT_RULES
from attest.results import CheckResult, Finding, Report, Severity
from attest.scoring.dispositions import apply_verdict_policy
from attest.scoring.verdict_policy import VerdictPolicy


def test_a_report_with_no_scored_check_has_no_overall_score():
    assert Report(results=[CheckResult(check="injection", passed=True)]).overall_score is None
    assert Report(results=[]).overall_score is None


def test_overall_score_averages_only_scored_checks():
    report = Report(
        results=[
            CheckResult(check="faithfulness", passed=True, score=None),
            CheckResult(check="tool_use", passed=True, score=0.5),
        ]
    )
    assert report.overall_score == 0.5
    assert '"overall_score":0.5' in report.model_dump_json()


def _warning(verdict: str, **metadata: object) -> Finding:
    return Finding(severity=Severity.WARN, verdict=verdict, subject="x", metadata=metadata)


def test_a_hand_built_all_unverifiable_faithfulness_result_needs_review():
    result = CheckResult(check="faithfulness", passed=True, findings=[_warning("unverifiable")])
    report = Report(results=[result])
    assert report.verdict == "review" and report.passed is False
    assert report.verdict == apply_verdict_policy(report).verdict


def test_an_unverifiable_claim_beside_a_supported_one_passes_as_under_the_policy():
    supported = Finding(severity=Severity.PASS, verdict="supported", subject="y")
    result = CheckResult(
        check="faithfulness", passed=True, findings=[supported, _warning("unverifiable")]
    )
    assert Report(results=[result]).verdict == "pass"


def test_a_hand_built_policy_warning_needs_review():
    report = Report(results=[CheckResult(check="policy", passed=True, findings=[_warning("w")])])
    assert report.verdict == "review" and report.passed is False


def test_a_hand_built_tool_use_error_follows_the_default_policy():
    result = CheckResult(check="tool_use", passed=False, findings=[_warning("error_silent")])
    assert Report(results=[result]).verdict == "review"


def test_an_assigned_disposition_wins_over_the_default():
    finding = _warning("unverifiable").model_copy(update={"disposition": "pass"})
    report = Report(results=[CheckResult(check="faithfulness", passed=True, findings=[finding])])
    assert report.verdict == "pass"


def test_an_unchecked_finding_from_any_check_needs_review():
    for check in ("custom", "role", "faithfulness"):
        finding = _warning("anything", checked=False)
        report = Report(results=[CheckResult(check=check, passed=True, findings=[finding])])
        assert report.verdict == "review"
        assert apply_verdict_policy(report).verdict == "review"


def test_the_default_rules_match_the_default_policy():
    policy = VerdictPolicy()
    assert DEFAULT_RULES.on_inconclusive_faithfulness == policy.on_inconclusive_faithfulness
    assert DEFAULT_RULES.on_injection_warning == policy.on_injection_warning
    assert DEFAULT_RULES.tool_use.model_dump() == policy.tool_use.model_dump()
