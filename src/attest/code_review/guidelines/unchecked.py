"""What the guideline check reports when a judge call fails: unchecked, never a clean pass."""

from __future__ import annotations

from ...results import CheckResult, Finding, Severity
from .models import Guideline, ReviewGuidelines

UNCHECKED = "unchecked"


def unchecked_result(check: str, guidelines: ReviewGuidelines, reason: str) -> CheckResult:
    """The whole output went unchecked: one warning, and `metadata["checked"]` false."""
    count = len(guidelines.rules)
    return CheckResult(
        check=check,
        passed=True,
        summary=f"Not checked against the {count} rules in {guidelines.name}.",
        findings=[
            Finding(
                severity=Severity.WARN,
                verdict=UNCHECKED,
                subject=guidelines.name,
                reason=reason,
                metadata={"checked": False},
            )
        ],
        metadata={
            "guidelines": guidelines.name,
            "rules": count,
            "builtin": guidelines.builtin,
            "checked": False,
        },
    )


def unconfirmed_break(rule: Guideline, quote: str, reason: str) -> Finding:
    """A reported break whose confirmation call failed: neither dropped nor silently discarded."""
    return Finding(
        severity=Severity.WARN,
        verdict=UNCHECKED,
        subject=f"{rule.id}: {rule.text}",
        reason=reason,
        evidence=quote,
        metadata={"rule": rule.id, "section": rule.section, "checked": False},
    )
