"""Run the claim extractor and verifier so a failure is inconclusive, never a pass."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field

from ..llm import BudgetExceeded, ProviderConfigError
from ..results import Finding
from ..utils.failures import failure_reason
from .claim_findings import unchecked, with_missing_claims

ExtractFn = Callable[[str], list[str]]
VerifyFn = Callable[[list[str], str], list[Finding]]

FAILED_EXTRACTION_SUBJECT = "final answer"


class Extraction(BaseModel):
    claims: list[str] = Field(default_factory=list[str])
    failure: Finding | None = None


def extract_safely(extract: ExtractFn, answer: str) -> Extraction:
    """The claims `extract` returns, or an unchecked finding when it raises or returns junk."""
    try:
        return Extraction(claims=list(extract(answer)))
    except (BudgetExceeded, ProviderConfigError):
        raise
    except Exception as error:
        reason = failure_reason("Claim extraction", error)
        return Extraction(failure=unchecked(FAILED_EXTRACTION_SUBJECT, reason))


def verify_safely(verify: VerifyFn, claims: list[str], evidence: str) -> list[Finding]:
    """One finding per claim; claims a failed or partial verifier didn't judge are unchecked."""
    try:
        return with_missing_claims(claims, list(verify(claims, evidence)))
    except (BudgetExceeded, ProviderConfigError):
        raise
    except Exception as error:
        reason = failure_reason("Claim verification", error)
        return [unchecked(claim, reason) for claim in claims]
