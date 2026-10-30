from __future__ import annotations

from ...content import Detection, TextSegment
from .patterns import RegexPattern

QUOTED_EXAMPLE_CONFIDENCE_FACTOR = 0.5
_EDUCATIONAL_WORDS = ("training", "example", "quoting", "quoted", "the phrase", "documentation")


def match_detection(
    segment: TextSegment,
    pattern: RegexPattern,
    start: int,
    end: int,
    *,
    detector: str,
    possible_threshold: float,
) -> Detection:
    quoted_example = quoted_educational_framing(segment.text, start, end)
    confidence = pattern.confidence * segment.extraction_confidence
    if quoted_example:
        confidence *= QUOTED_EXAMPLE_CONFIDENCE_FACTOR
    return Detection(
        verdict="possible_injection" if confidence < possible_threshold else "suspicious",
        detector=detector,
        category=pattern.category,
        matched_text=_match_context(segment.text, start, end),
        location=segment.location,
        subject=segment.subject,
        step=segment.step,
        confidence=confidence,
        metadata={
            **segment.metadata,
            "pattern": pattern.name,
            "pattern_severity": pattern.severity,
            "char_start": start,
            "char_end": end,
            "quoted_educational_framing": quoted_example,
        },
    )


def timeout_detection(
    segment: TextSegment,
    pattern: str,
    *,
    patterns_attempted: int,
    patterns_skipped: int,
) -> Detection:
    return Detection(
        verdict="unscanned_content",
        detector="regex",
        category="scan_timeout",
        matched_text="",
        location=segment.location,
        subject=segment.subject,
        step=segment.step,
        confidence=0,
        metadata={
            **segment.metadata,
            "pattern": pattern,
            "patterns_attempted": patterns_attempted,
            "patterns_skipped": patterns_skipped,
            "coverage_complete": False,
        },
    )


def quoted_educational_framing(text: str, start: int, end: int) -> bool:
    nearby = text[max(0, start - 100) : min(len(text), end + 100)].lower()
    educational = any(word in nearby for word in _EDUCATIONAL_WORDS)
    before, after = text[:start], text[end:]
    double_open = before.rfind('"')
    double_close = after.find('"')
    # Apostrophes are deliberately not treated as quote delimiters: contractions are common
    # in attacker-controlled prose and cannot safely establish educational framing.
    inside_double_quotes = double_open >= 0 and double_close >= 0
    return educational and inside_double_quotes


def _match_context(text: str, start: int, end: int) -> str:
    return text[max(0, start - 15) : min(len(text), end + 45)].strip()
