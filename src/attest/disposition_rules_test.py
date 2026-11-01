"""A finding nothing checked goes to review, unless its check's rule is stricter."""

import pytest

from attest.disposition_rules import DEFAULT_RULES, disposition_for, result_dispositions
from attest.results import Finding, Severity
from attest.scoring.verdict_policy import ToolUsePolicy, VerdictPolicy

PASS, WARN, FAIL = Severity.PASS, Severity.WARN, Severity.FAIL


def _unjudged(verdict: str, severity: Severity = WARN) -> Finding:
    return Finding(severity=severity, verdict=verdict, metadata={"checked": False})


def test_an_unjudged_injection_warning_blocks_when_warnings_block():
    policy = VerdictPolicy(on_injection_warning="block")
    assert disposition_for("injection", _unjudged("suspicious"), policy) == "block"
    unchecked = Finding(severity=WARN, verdict="unchecked")
    assert disposition_for("injection", unchecked, policy) == "block"


@pytest.mark.parametrize(
    ("verdict", "field"),
    [
        ("disallowed_tool", "on_disallowed_tool"),
        ("error_silent", "on_unhandled_error"),
        ("error_claimed_success", "on_claimed_success"),
        ("unnecessary_call", "on_unnecessary_call"),
    ],
)
def test_an_unjudged_tool_use_finding_keeps_a_blocking_rule(verdict, field):
    blocking = VerdictPolicy(tool_use=ToolUsePolicy(**{field: "block"}))
    passing = VerdictPolicy(tool_use=ToolUsePolicy(**{field: "pass"}))
    assert disposition_for("tool_use", _unjudged(verdict), blocking) == "block"
    assert disposition_for("tool_use", _unjudged(verdict), passing) == "review"


@pytest.mark.parametrize("check", ["role", "policy", "custom", "code_injection", "tool_use"])
def test_an_unchecked_failure_blocks_and_an_unchecked_warning_needs_review(check):
    assert disposition_for(check, Finding(severity=FAIL, verdict="unchecked"), DEFAULT_RULES) == (
        "block"
    )
    assert disposition_for(check, Finding(severity=WARN, verdict="unchecked"), DEFAULT_RULES) == (
        "review"
    )


def test_always_blocking_verdicts_still_block_when_unjudged():
    assert disposition_for("injection", _unjudged("compromised"), DEFAULT_RULES) == "block"
    assert disposition_for("role", _unjudged("out_of_scope_complied"), DEFAULT_RULES) == "block"


def test_an_unjudged_supported_claim_needs_review_on_its_own():
    assert disposition_for("faithfulness", _unjudged("supported", PASS), DEFAULT_RULES) == "review"


def test_inconclusive_faithfulness_set_to_pass_lets_unchecked_claims_pass():
    policy = VerdictPolicy(on_inconclusive_faithfulness="pass")
    supported = Finding(severity=PASS, verdict="supported")
    findings = [supported, _unjudged("unverifiable")]
    assert result_dispositions("faithfulness", findings, policy) == ["pass", "pass"]
    assert result_dispositions("faithfulness", findings, DEFAULT_RULES) == ["pass", "review"]
