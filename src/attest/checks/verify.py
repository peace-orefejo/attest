"""Faithfulness: verify each claim in the final answer against the real tool outputs."""

from __future__ import annotations

from typing import Callable, Literal

from pydantic import BaseModel

from ..core.llm import call
from ..core import CheckResult, Finding, Severity, Trajectory
from .profiles import get_profile
from .profiles.registry import PROFILE_KINDS

_SEVERITY = {
    "supported": Severity.PASS,
    "unsupported": Severity.FAIL,
    "unverifiable": Severity.WARN,
}

MAX_CLAIMS = 40
BATCH_SIZE = 15


class ClaimsOut(BaseModel):
    """The list of atomic factual claims found in the text."""

    claims: list[str]


class VerdictOut(BaseModel):
    """Whether the evidence supports the claim, with a reason and the deciding span."""

    verdict: Literal["supported", "unsupported", "unverifiable"]
    reason: str = ""
    evidence_quote: str | None = None


class _ClaimVerdict(BaseModel):
    """A verdict for one numbered claim."""

    claim: int
    verdict: Literal["supported", "unsupported", "unverifiable"]
    reason: str = ""
    evidence_quote: str | None = None


class _BatchOut(BaseModel):
    """One verdict for each numbered claim."""

    verdicts: list[_ClaimVerdict]


ExtractFn = Callable[[str], list[str]]
VerifyFn = Callable[[list[str], str], list[Finding]]


def judge_trajectory(traj: Trajectory, extract: ExtractFn, verify: VerifyFn,
                     *, max_claims: int = MAX_CLAIMS) -> CheckResult:
    evidence = traj.evidence()
    claims = extract(traj.final_answer)
    capped = len(claims) > max_claims
    if capped:
        claims = claims[:max_claims]
    findings = verify(claims, evidence)
    supported = sum(f.verdict == "supported" for f in findings)
    unsupported = sum(f.verdict == "unsupported" for f in findings)
    checkable = supported + unsupported
    rate: float | None = supported / checkable if checkable else 1.0
    summary = f"{supported}/{checkable} checkable claims grounded."
    if findings and not checkable:
        rate = None
        summary = f"None of the {len(findings)} claims could be checked against the evidence."
    if capped:
        summary += f" (checked the first {max_claims} claims)"
    return CheckResult(
        check="faithfulness",
        passed=unsupported == 0,
        score=rate,
        summary=summary,
        findings=findings,
    )


_EXTRACT_SYSTEM = get_profile("factual").extract_prompt
_VERIFY_SYSTEM = {kind: get_profile(kind).verify_prompt for kind in PROFILE_KINDS}


def extract_claims(final_answer: str, *, answer_kind: str = "factual",
                   task: str | None = None) -> list[str]:
    """Split a final answer into atomic, individually-checkable claims for `answer_kind`.

    `task` is the request the answer responds to. It is used only to make claims
    self-contained, never as a source of claims.
    """
    system = get_profile(answer_kind).extract_prompt
    if not final_answer.strip():
        return []
    context = (f"Task the answer responds to (context only, do not extract claims from it):\n"
               f"{task}\n\n") if task and task.strip() else ""
    return call(
        system=system,
        user=f"{context}Final answer to decompose:\n\n{final_answer}",
        output=ClaimsOut,
    ).claims


def grounded_verifier(claim: str, evidence: str, *, answer_kind: str = "factual") -> Finding:
    """Decide whether `evidence` entails one `claim`. Sees no agent reasoning."""
    system = get_profile(answer_kind).verify_prompt
    if not evidence.strip():
        return Finding(
            severity=Severity.WARN,
            verdict="unverifiable",
            subject=claim,
            reason="No tool-output evidence was recorded.",
        )
    out = call(
        system=system,
        user=f"CLAIM:\n{claim}\n\nEVIDENCE (the agent's real tool outputs):\n{evidence}",
        output=VerdictOut,
    )
    return Finding(
        severity=_SEVERITY[out.verdict],
        verdict=out.verdict,
        subject=claim,
        reason=out.reason,
        evidence=out.evidence_quote or None,
    )


_BATCH_INSTRUCTION = (
    "You are given several NUMBERED claims and one EVIDENCE block. Apply the standard below "
    "to EACH claim independently, using ONLY the evidence. Return exactly one verdict per "
    "claim: its number, the verdict, a brief reason, and the deciding span from the evidence. "
    "Do not skip or merge claims.\n\nSTANDARD:\n"
)


def _batch_system(answer_kind: str) -> str:
    return _BATCH_INSTRUCTION + get_profile(answer_kind).verify_prompt


def _verify_batch(batch: list[str], evidence: str, system: str) -> list[Finding]:
    numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(batch, start=1))
    try:
        out = call(
            system=system,
            user=f"CLAIMS:\n{numbered}\n\nEVIDENCE (the agent's real tool outputs):\n{evidence}",
            output=_BatchOut,
            max_tokens=8192,
        )
        by_num = {v.claim: v for v in out.verdicts}
    except Exception:
        by_num = {}
    findings: list[Finding] = []
    for i, claim in enumerate(batch, start=1):
        v = by_num.get(i)
        if v is None:
            findings.append(Finding(
                severity=Severity.WARN, verdict="unverifiable", subject=claim,
                reason="No verdict was returned for this claim."))
        else:
            findings.append(Finding(
                severity=_SEVERITY[v.verdict], verdict=v.verdict, subject=claim,
                reason=v.reason, evidence=v.evidence_quote or None))
    return findings


def verify_claims(claims: list[str], evidence: str, *, answer_kind: str = "factual",
                  batch_size: int = BATCH_SIZE) -> list[Finding]:
    """Verify many claims against the evidence in batched calls (one call per batch)."""
    system = _batch_system(answer_kind)
    if not claims:
        return []
    if not evidence.strip():
        return [Finding(severity=Severity.WARN, verdict="unverifiable", subject=c,
                        reason="No tool-output evidence was recorded.") for c in claims]
    findings: list[Finding] = []
    for start in range(0, len(claims), batch_size):
        findings.extend(_verify_batch(claims[start:start + batch_size], evidence, system))
    return findings
