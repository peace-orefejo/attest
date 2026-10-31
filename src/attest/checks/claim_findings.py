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


def unchecked(claim: str, reason: str) -> Finding:
    """An `unverifiable` finding for a claim no verifier judged, so it can never read as a pass."""
    finding = unverifiable(claim, reason)
    finding.metadata["checked"] = False
    return finding


def is_unchecked(finding: Finding) -> bool:
    """A faithfulness finding for a claim that was never judged: a failed or skipped call."""
    return finding.verdict == "unverifiable" and finding.metadata.get("checked") is False


def faithfulness_summary(supported: int, checkable: int, total: int) -> str:
    if total and not checkable:
        return f"None of the {total} claims could be checked against the evidence."
    return f"{supported}/{checkable} checkable claims grounded."


def with_missing_claims(claims: list[str], findings: list[Finding]) -> list[Finding]:
    """Add an `unverifiable` finding for each claim the verifier returned no verdict for.

    A verifier that drops claims must not make the answer look verified: a missing verdict
    is inconclusive (`checked` is false), never a pass.
    """
    missing = len(claims) - len(findings)
    if missing <= 0:
        return findings
    returned = {finding.subject for finding in findings}
    unanswered = [claim for claim in claims if claim not in returned] + claims
    reason = "The verifier returned no verdict for this claim."
    return findings + [unchecked(claim, reason) for claim in unanswered[:missing]]
