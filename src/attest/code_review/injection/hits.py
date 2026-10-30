"""Hit and match records shared by the detectors, plus window and overlap helpers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .segments import Segment

WINDOW_CHARS = 300


class Hit(BaseModel):
    """One scored detection in a segment, with the text around it for confirmation."""

    model_config = ConfigDict(frozen=True)

    segment: Segment
    detector: str
    pattern: str
    category: str
    confidence: float
    line: int
    evidence: str
    window: str


class Match(BaseModel):
    """A regex match before context scoring, with offsets in the scanned text."""

    model_config = ConfigDict(frozen=True)

    detector: str
    pattern: str
    category: str
    confidence: float
    start: int
    end: int
    educational: bool


class HitScan(BaseModel):
    hits: list[Hit]
    incomplete: bool


class MatchScan(BaseModel):
    matches: list[Match]
    incomplete: bool


def window(text: str, start: int, end: int) -> str:
    return text[max(0, start - WINDOW_CHARS) : end + WINDOW_CHARS]


def strongest(matches: list[Match]) -> list[Match]:
    """Keep the most confident match of each overlapping group, in text order."""
    kept: list[Match] = []
    for match in sorted(matches, key=lambda m: -m.confidence):
        if not any(match.start < k.end and k.start < match.end for k in kept):
            kept.append(match)
    return sorted(kept, key=lambda m: m.start)
