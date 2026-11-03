"""check_guidelines: does one review output follow the team's review rules?"""

from __future__ import annotations

from ...llm import BudgetExceeded, ProviderConfigError, call
from ...prompts.code_review.guidelines import CHECK_PROMPT, check_user
from ...results import CheckResult, Finding, Severity
from ...utils.failures import failure_reason
from ..models import ReviewOutput
from .confirm import ConfirmOut, confirm_break
from .evidence import fit_evidence
from .models import ReviewGuidelines
from .unchecked import UNCHECKED, unchecked_result, unconfirmed_break
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
    If a judge call fails (anything but `BudgetExceeded` or `ProviderConfigError`), what it
    covered is reported `unchecked`, never as following the rules, and the gate drops the output.
    """
    try:
        answer = call(
            system=CHECK_PROMPT,
            user=_user(output, guidelines, evidence),
            output=ViolationsOut,
            site="guidelines.check",
        )
    except (BudgetExceeded, ProviderConfigError):
        raise
    except Exception as error:
        reason = failure_reason("The guideline check", error)
        return unchecked_result(GUIDELINES_CHECK, guidelines, reason)
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
    failed_confirms = sum(f.verdict == UNCHECKED for f in findings)
    return CheckResult(
        check=GUIDELINES_CHECK,
        passed=not broken,
        summary=_summary(findings, broken, failed_confirms, guidelines),
        findings=findings,
        metadata={
            "guidelines": guidelines.name,
            "rules": len(guidelines.rules),
            "discarded": len(answer.violations) - len(accepted),
            "unconfirmed": unconfirmed,
            "confirm_failed": failed_confirms,
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
        verdict = _confirm(item, output)
        if isinstance(verdict, Finding):
            return verdict
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


def _confirm(item: Accepted, output: ReviewOutput) -> ConfirmOut | Finding:
    quote = item.violation.quote
    try:
        return confirm_break(item.rule, output, quote)
    except (BudgetExceeded, ProviderConfigError):
        raise
    except Exception as error:
        reason = failure_reason("Confirming this break", error)
        return unconfirmed_break(item.rule, quote, reason)


def _summary(
    findings: list[Finding], broken: int, unchecked: int, guidelines: ReviewGuidelines
) -> str:
    count = len(guidelines.rules)
    missed = len(findings) - broken - unchecked
    not_confirmed = f" {unchecked} reported break(s) could not be checked." if unchecked else ""
    if not (broken or missed):
        if unchecked:
            return f"No confirmed break of the {count} rules in {guidelines.name}.{not_confirmed}"
        return f"Follows all {count} rules in {guidelines.name}."
    parts = [f"breaks {broken}"] * bool(broken) + [f"misses {missed}"] * bool(missed)
    joined = " and ".join(parts).capitalize()
    return f"{joined} of {count} rules in {guidelines.name}.{not_confirmed}"
