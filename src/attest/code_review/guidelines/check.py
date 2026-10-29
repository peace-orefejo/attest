"""check_guidelines: does one review output follow the team's review rules?"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from ...core import CheckResult, Finding, Severity
from ...core.llm import call
from ..models import ReviewOutput
from .confirm import confirm_break
from .models import Guideline, ReviewGuidelines
from .prompts import CHECK_PROMPT

GUIDELINES_CHECK = "guidelines"
BROKEN = "breaks_guideline"
MISSED = "misses_guideline"
MAX_EVIDENCE_CHARS = 60_000
MIN_QUOTE_WORDS = 3


class Violation(BaseModel):
    rule: str
    kind: Literal["breaks", "misses"] = "breaks"
    quote: str
    reason: str = ""


class ViolationsOut(BaseModel):
    violations: list[Violation] = Field(default_factory=list)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _quotes_output(quote: str, text: str) -> bool:
    if not quote or quote not in text:
        return False
    return len(quote.split()) >= MIN_QUOTE_WORDS or quote == text


def _accepted(violations: list[Violation], guidelines: ReviewGuidelines, text: str) -> list[tuple[Violation, Guideline]]:
    valid: dict[tuple[str, str], tuple[Violation, Guideline]] = {}
    for violation in violations:
        rule = guidelines.get(violation.rule.strip().upper())
        if rule is None or not _quotes_output(_norm(violation.quote), text):
            continue
        valid.setdefault((rule.id, violation.kind), (violation, rule))
    broken = {rule_id for rule_id, kind in valid if kind == "breaks"}
    return [pair for (rule_id, kind), pair in valid.items() if kind == "breaks" or rule_id not in broken]


def _prompt(output: ReviewOutput, guidelines: ReviewGuidelines, evidence: str) -> str:
    question = f"Question it answers: {output.question}\n" if output.question else ""
    return (
        f"Review rules ({guidelines.name}):\n{guidelines.render()}\n\n"
        f"Evidence the reviewer saw:\n{evidence[:MAX_EVIDENCE_CHARS]}\n\n"
        f"Output type: {output.output_type}\n{question}"
        f"Output to check:\n{output.text}"
    )


def _finding(violation: Violation, rule: Guideline, guidelines: ReviewGuidelines) -> Finding:
    breaks = violation.kind == "breaks"
    return Finding(
        severity=Severity.FAIL if breaks else Severity.WARN, verdict=BROKEN if breaks else MISSED,
        subject=f"{rule.id}: {rule.text}",
        reason=violation.reason, evidence=violation.quote,
        metadata={"rule": rule.id, "section": rule.section, "source": rule.source or guidelines.name},
    )


def check_guidelines(output: ReviewOutput, guidelines: ReviewGuidelines, *, evidence: str = "") -> CheckResult:
    """Judge whether a review output breaks or misses any rule; each report must quote the output exactly.

    A break fails the check. A miss is a warning: the output left out something a rule asks for.
    A quote must be at least three words, or the whole output. A break hides a miss of the same rule.
    Each break is confirmed by a second call; an unconfirmed break is discarded.
    """
    answer = call(system=CHECK_PROMPT, user=_prompt(output, guidelines, evidence), output=ViolationsOut)
    accepted = _accepted(answer.violations, guidelines, _norm(output.text))
    findings: list[Finding] = []
    unconfirmed = 0
    for violation, rule in accepted:
        if violation.kind == "breaks":
            verdict = confirm_break(rule, output, violation.quote)
            if not verdict.breaks:
                unconfirmed += 1
                continue
            violation = violation.model_copy(update={"reason": verdict.reason or violation.reason})
        findings.append(_finding(violation, rule, guidelines))
    discarded = len(answer.violations) - len(accepted)
    count = len(guidelines.rules)
    broken = sum(f.severity is Severity.FAIL for f in findings)
    missed = len(findings) - broken
    parts = [f"breaks {broken}"] * bool(broken) + [f"misses {missed}"] * bool(missed)
    summary = (f"Follows all {count} rules in {guidelines.name}." if not findings
               else f"{' and '.join(parts).capitalize()} of {count} rules in {guidelines.name}.")
    return CheckResult(
        check=GUIDELINES_CHECK, passed=not broken, summary=summary, findings=findings,
        metadata={"guidelines": guidelines.name, "rules": count, "discarded": discarded,
                  "unconfirmed": unconfirmed, "builtin": guidelines.builtin},
    )
