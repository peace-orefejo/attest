"""Faithfulness: verify each claim in the final answer against the real tool outputs."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from ..llm import BudgetExceeded, call
from ..prompts.faithfulness import (
    batch_system,
    claims_user,
    evidence_prefix,
    extract_user,
    verify_user,
)
from ..results import CheckResult, Finding
from ..trajectory import Trajectory
from .artifact_evidence import ArtifactExtraction, current_extraction, gather_evidence
from .claim_findings import (
    NO_EVIDENCE_REASON,
    ClaimVerdict,
    faithfulness_summary,
    unverifiable,
    verdict_finding,
)
from .profiles import get_profile
from .provenance import with_locations

MAX_CLAIMS = 40
BATCH_SIZE = 15


class ClaimsOut(BaseModel):
    """The list of atomic factual claims found in the text."""

    claims: list[str]


class VerdictOut(BaseModel):
    """Whether the evidence supports the claim, with a reason and the deciding span."""

    verdict: ClaimVerdict
    reason: str = ""
    evidence_quote: str | None = None


class _ClaimVerdict(BaseModel):
    """A verdict for one numbered claim."""

    claim: int
    verdict: ClaimVerdict
    reason: str = ""
    evidence_quote: str | None = None


class _BatchOut(BaseModel):
    """One verdict for each numbered claim."""

    verdicts: list[_ClaimVerdict]


ExtractFn = Callable[[str], list[str]]
VerifyFn = Callable[[list[str], str], list[Finding]]


def judge_trajectory(
    traj: Trajectory,
    extract: ExtractFn,
    verify: VerifyFn,
    *,
    max_claims: int = MAX_CLAIMS,
    artifacts: ArtifactExtraction | None = None,
) -> CheckResult:
    """Grade the answer's claims; `artifacts` overrides the active artifact extraction."""
    claims = extract(traj.final_answer)
    capped = len(claims) > max_claims
    evidence = gather_evidence(traj, artifacts or current_extraction())
    findings = with_locations(verify(claims[:max_claims], evidence.text), evidence.blocks)
    supported = sum(finding.verdict == "supported" for finding in findings)
    unsupported = sum(finding.verdict == "unsupported" for finding in findings)
    checkable = supported + unsupported
    unscorable = bool(findings) and not checkable
    summary = faithfulness_summary(supported, checkable, len(findings))
    if capped:
        summary += f" (checked the first {max_claims} claims)"
    return CheckResult(
        check="faithfulness",
        passed=unsupported == 0,
        score=None if unscorable else (supported / checkable if checkable else 1.0),
        summary=summary,
        findings=findings,
        metadata={
            **evidence.metadata(),
            "claims_checked": checkable,
            "claims_total": len(findings),
        },
    )


def extract_claims(
    final_answer: str, *, answer_kind: str = "factual", task: str | None = None
) -> list[str]:
    """Split a final answer into atomic, individually-checkable claims for `answer_kind`.

    `task` is the request the answer responds to. It is used only to make claims
    self-contained, never as a source of claims.
    """
    system = get_profile(answer_kind).extract_prompt
    if not final_answer.strip():
        return []
    return call(system=system, user=extract_user(final_answer, task), output=ClaimsOut).claims


def grounded_verifier(claim: str, evidence: str, *, answer_kind: str = "factual") -> Finding:
    """Decide whether `evidence` entails one `claim`. Sees no agent reasoning."""
    system = get_profile(answer_kind).verify_prompt
    if not evidence.strip():
        return unverifiable(claim, NO_EVIDENCE_REASON)
    out = call(
        system=system,
        user=verify_user(claim, evidence),
        output=VerdictOut,
    )
    return verdict_finding(claim, out.verdict, out.reason, out.evidence_quote)


def verify_claims(
    claims: list[str],
    evidence: str,
    *,
    answer_kind: str = "factual",
    batch_size: int = BATCH_SIZE,
) -> list[Finding]:
    """Verify many claims against the evidence in batched calls (one call per batch)."""
    system = batch_system(get_profile(answer_kind).verify_prompt)
    if not claims:
        return []
    if not evidence.strip():
        return [unverifiable(claim, NO_EVIDENCE_REASON) for claim in claims]
    shared = len(claims) > batch_size
    findings: list[Finding] = []
    for start in range(0, len(claims), batch_size):
        batch = claims[start : start + batch_size]
        findings.extend(_verify_batch(batch, evidence, system, shared=shared))
    return findings


def _verify_batch(
    batch: list[str], evidence: str, system: str, *, shared: bool = False
) -> list[Finding]:
    verdicts = _batch_verdicts(batch, evidence, system, shared=shared)
    findings: list[Finding] = []
    for number, claim in enumerate(batch, start=1):
        verdict = verdicts.get(number)
        if verdict is None:
            findings.append(unverifiable(claim, "No verdict was returned for this claim."))
            continue
        findings.append(
            verdict_finding(claim, verdict.verdict, verdict.reason, verdict.evidence_quote)
        )
    return findings


def _batch_verdicts(
    batch: list[str], evidence: str, system: str, *, shared: bool
) -> dict[int, _ClaimVerdict]:
    try:
        out = call(
            system=system,
            prefix=evidence_prefix(evidence),
            user=claims_user(batch),
            output=_BatchOut,
            max_tokens=8192,
            reuse="prefix" if shared else None,
        )
    except BudgetExceeded:
        raise
    except Exception:
        return {}
    return {verdict.claim: verdict for verdict in out.verdicts}
