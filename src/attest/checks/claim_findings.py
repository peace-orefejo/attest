"""Build faithfulness findings and summaries from claim verdicts."""

from __future__ import annotations

from typing import Literal

from ..results import Finding, Severity

ClaimVerdict = Literal["supported", "unsupported", "unverifiable"]

NO_EVIDENCE_REASON = "No tool-output evidence was recorded."

_SEVERITY: dict[ClaimVerdict, Severity] = {
    "supported": Severity.PASS,
    "unsupported": Severity.FAIL,
    "unverifiable": Severity.WARN,
}


def verdict_finding(
    claim: str, verdict: ClaimVerdict, reason: str, evidence_quote: str | None
) -> Finding:
    return Finding(
        severity=_SEVERITY[verdict],
        verdict=verdict,
        subject=claim,
        reason=reason,
        evidence=evidence_quote or None,
    )


def unverifiable(claim: str, reason: str) -> Finding:
    return Finding(severity=Severity.WARN, verdict="unverifiable", subject=claim, reason=reason)


def faithfulness_summary(supported: int, checkable: int, total: int) -> str:
    if total and not checkable:
        return f"None of the {total} claims could be checked against the evidence."
    return f"{supported}/{checkable} checkable claims grounded."
