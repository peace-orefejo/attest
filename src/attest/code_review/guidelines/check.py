"""check_guidelines: does one review output follow the team's review rules?"""

from __future__ import annotations

from ...llm import call
from ...prompts.code_review.guidelines import CHECK_PROMPT, check_user
from ...results import CheckResult, Finding, Severity
from ..models import ReviewOutput
from .confirm import confirm_break
from .evidence import fit_evidence
from .models import ReviewGuidelines
from .violations import Accepted, Violation, ViolationsOut, accept, normalize

GUIDELINES_CHECK = "guidelines"
BROKEN = "breaks_guideline"
MISSED = "misses_guideline"
MAX_EVIDENCE_CHARS = 60_000

__all__ = [
    "BROKEN",
    "CHECK_PROMPT",
    "GUIDELINES_CHECK",
    "MAX_EVIDENCE_CHARS",
    "MISSED",
    "Violation",
    "ViolationsOut",
    "check_guidelines",
]


def check_guidelines(
    output: ReviewOutput, guidelines: ReviewGuidelines, *, evidence: str = ""
) -> CheckResult:
    """Judge whether a review output breaks or misses any rule; each report quotes the output.

    A break fails the check. A miss is a warning: the output left out something a rule asks for.
    A quote must be at least three words, or the whole output. A break hides a miss of the
    same rule.
    Each break is confirmed by a second call; an unconfirmed break is discarded.
    """
    answer = call(
        system=CHECK_PROMPT, user=_user(output, guidelines, evidence), output=ViolationsOut
    )
    accepted = accept(answer.violations, guidelines, normalize(output.text))
    findings: list[Finding] = []
    unconfirmed = 0
    for item in accepted:
        finding = _confirmed_finding(item, output, guidelines)
        if finding is None:
            unconfirmed += 1
            continue
        findings.append(finding)
    broken = sum(f.severity is Severity.FAIL for f in findings)
    return CheckResult(
        check=GUIDELINES_CHECK,
        passed=not broken,
        summary=_summary(findings, broken, guidelines),
        findings=findings,
        metadata={
            "guidelines": guidelines.name,
            "rules": len(guidelines.rules),
            "discarded": len(answer.violations) - len(accepted),
            "unconfirmed": unconfirmed,
            "builtin": guidelines.builtin,
        },
    )


def _user(output: ReviewOutput, guidelines: ReviewGuidelines, evidence: str) -> str:
    return check_user(
        rules_name=guidelines.name,
        rules=guidelines.render(),
        evidence=fit_evidence(evidence, MAX_EVIDENCE_CHARS),
        output_type=output.output_type,
        question=output.question,
        text=output.text,
    )


def _confirmed_finding(
    item: Accepted, output: ReviewOutput, guidelines: ReviewGuidelines
) -> Finding | None:
    violation = item.violation
    if violation.kind == "breaks":
        verdict = confirm_break(item.rule, output, violation.quote)
        if not verdict.breaks:
            return None
        violation = violation.model_copy(update={"reason": verdict.reason or violation.reason})
    breaks = violation.kind == "breaks"
    rule = item.rule
    return Finding(
        severity=Severity.FAIL if breaks else Severity.WARN,
        verdict=BROKEN if breaks else MISSED,
        subject=f"{rule.id}: {rule.text}",
        reason=violation.reason,
        evidence=violation.quote,
        metadata={
            "rule": rule.id,
            "section": rule.section,
            "source": rule.source or guidelines.name,
        },
    )


def _summary(findings: list[Finding], broken: int, guidelines: ReviewGuidelines) -> str:
    count = len(guidelines.rules)
    if not findings:
        return f"Follows all {count} rules in {guidelines.name}."
    missed = len(findings) - broken
    parts = [f"breaks {broken}"] * bool(broken) + [f"misses {missed}"] * bool(missed)
    return f"{' and '.join(parts).capitalize()} of {count} rules in {guidelines.name}."
