"""Build faithfulness findings and summaries from claim verdicts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..disposition_rules import is_unchecked_claim
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
    return is_unchecked_claim(finding)


def over_cap_findings(claims: list[str], max_claims: int) -> list[Finding]:
    """An unchecked finding for each claim past `max_claims`, so a capped answer can't pass."""
    reason = (
        f"Not checked: the answer makes {len(claims)} claims and faithfulness checks at most "
        f"{max_claims} (max_claims)."
    )
    return [unchecked(claim, reason) for claim in claims[max_claims:]]


def cap_note(total: int, max_claims: int) -> str:
    """The summary's note on claims past `max_claims`."""
    if max_claims == 0:
        return " (max_claims is 0, so no claim was checked)"
    first = "the first claim" if max_claims == 1 else f"the first {max_claims} claims"
    rest = total - max_claims
    more = "1 more was" if rest == 1 else f"{rest} more were"
    return f" (checked {first}; {more} not checked)"


class ClaimTally(BaseModel):
    """How many faithfulness findings are supported, unsupported, and in total."""

    supported: int
    unsupported: int
    total: int

    @classmethod
    def of(cls, findings: list[Finding]) -> ClaimTally:
        return cls(
            supported=sum(finding.verdict == "supported" for finding in findings),
            unsupported=sum(finding.verdict == "unsupported" for finding in findings),
            total=len(findings),
        )

    @property
    def checkable(self) -> int:
        return self.supported + self.unsupported

    @property
    def score(self) -> float | None:
        """Supported share of checkable claims; None when there are claims but none checkable."""
        if not self.checkable:
            return None if self.total else 1.0
        return self.supported / self.checkable


def claims_summary(tally: ClaimTally, claims: int, max_claims: int, *, extracted: bool) -> str:
    """The faithfulness summary, with a note when claims past `max_claims` went unchecked."""
    summary = (
        faithfulness_summary(tally.supported, tally.checkable, tally.total)
        if extracted
        else "The answer's claims could not be extracted, so none were checked."
    )
    return summary + cap_note(claims, max_claims) if claims > max_claims else summary


def faithfulness_summary(supported: int, checkable: int, total: int) -> str:
    if total and not checkable:
        return f"None of the {total} claims could be checked against the evidence."
    return f"{supported}/{checkable} checkable claims grounded."


def with_missing_claims(claims: list[str], findings: list[Finding]) -> list[Finding]:
    """Add an `unverifiable` finding for each claim the verifier returned no verdict for.

    A verifier that drops claims must not make the answer look verified: a missing verdict
    is inconclusive (`checked` is false), never a pass.
    """
    returned = {finding.subject for finding in findings}
    unanswered = [claim for claim in claims if claim not in returned]
    unmatched = sum(finding.subject not in claims for finding in findings)
    missing = max(len(claims) - len(findings), len(unanswered) - unmatched)
    if missing <= 0:
        return findings
    unanswered += claims
    reason = "The verifier returned no verdict for this claim."
    return findings + [unchecked(claim, reason) for claim in unanswered[:missing]]
