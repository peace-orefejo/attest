"""Combine detection confidence, confirmation and effect into one verdict."""

from __future__ import annotations

from typing import Iterable, Literal, cast

from ...core import Severity
from ..models import INJECTION_VERDICTS, InjectionVerdict

HIGH_CONFIDENCE = 0.9
MEDIUM_CONFIDENCE = 0.45

Tier = Literal["high", "medium", "low"]

_SEVERITY: dict[str, Severity] = {
    "clean": Severity.PASS,
    "suspicious": Severity.WARN,
    "payload": Severity.FAIL,
    "compromised": Severity.FAIL,
}


def tier(confidence: float) -> Tier:
    if confidence >= HIGH_CONFIDENCE:
        return "high"
    return "medium" if confidence >= MEDIUM_CONFIDENCE else "low"


def hit_verdict(confidence: float, confirmed: bool | None) -> InjectionVerdict:
    """Verdict for one hit: high is payload, low is clean, medium needs a confirmation."""
    level = tier(confidence)
    if level == "high":
        return "payload"
    if level == "low":
        return "clean"
    return "payload" if confirmed else "suspicious"


def with_effect(verdict: InjectionVerdict, obeyed: bool) -> InjectionVerdict:
    """Upgrade a payload to compromised when a review output obeyed it."""
    return "compromised" if verdict == "payload" and obeyed else verdict


def overall(verdicts: Iterable[str], *, coverage_incomplete: bool = False) -> InjectionVerdict:
    """The most severe verdict; never clean when coverage was incomplete."""
    rank = max((INJECTION_VERDICTS.index(v) for v in verdicts), default=0)
    if coverage_incomplete:
        rank = max(rank, INJECTION_VERDICTS.index("suspicious"))
    return cast(InjectionVerdict, INJECTION_VERDICTS[rank])


def severity(verdict: str) -> Severity:
    return _SEVERITY[verdict]


def blocks(verdict: str) -> bool:
    return verdict in ("payload", "compromised")
