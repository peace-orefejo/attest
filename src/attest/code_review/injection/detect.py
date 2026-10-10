"""Run the deterministic detectors over segments and score each hit."""

from __future__ import annotations

from dataclasses import dataclass

from ...checks.injection import (
    DEFAULT_DETECTORS,
    EncodedPayloadDetector,
    InjectionDetector,
    RegexDetector,
    UnicodeDetector,
)
from ...checks.injection.detectors.hidden_unicode import first_bidi, suspicious_unicode
from ...content import TextSegment
from ...utils.encoded_scan import find_encoded
from .context import GENERIC_FACTOR, PROSE_BAIT_FACTOR, REFERENCE_FACTOR, reference_example
from .patterns import APPROVAL_BAIT, CODE_REVIEW_PATTERNS
from .segments import Segment

DIRECTIVE_KINDS = frozenset({"comment", "docstring", "string", "prose"})
WINDOW_CHARS = 300
_CODE_REVIEW = RegexDetector(CODE_REVIEW_PATTERNS)
_SCORED_HERE = (UnicodeDetector, EncodedPayloadDetector)


@dataclass(frozen=True)
class Hit:
    segment: Segment
    detector: str
    pattern: str
    category: str
    confidence: float
    line: int
    evidence: str
    window: str


@dataclass(frozen=True)
class _Match:
    detector: str
    pattern: str
    category: str
    confidence: float
    start: int
    end: int
    educational: bool


def _window(text: str, start: int, end: int) -> str:
    return text[max(0, start - WINDOW_CHARS):end + WINDOW_CHARS]


def _regex_matches(text: str) -> tuple[list[_Match], bool]:
    segment = TextSegment(text=text, location="", source_kind="code_review", subject="")
    sources: list[tuple[str, InjectionDetector]] = [
        ("regex", d) for d in DEFAULT_DETECTORS if not isinstance(d, _SCORED_HERE)
    ]
    sources.append(("code_review", _CODE_REVIEW))
    matches: list[_Match] = []
    incomplete = False
    for label, detector in sources:
        for detection in detector.scan(segment):
            if detection.verdict == "unscanned_content":
                incomplete = True
                continue
            meta = detection.metadata
            factor = GENERIC_FACTOR if label == "regex" else 1.0
            matches.append(_Match(
                label, str(meta.get("pattern", detection.category)), detection.category,
                detection.confidence * factor, int(meta.get("char_start", 0)),
                int(meta.get("char_end", len(text))), bool(meta.get("quoted_educational_framing")),
            ))
    return _strongest(matches), incomplete


def _strongest(matches: list[_Match]) -> list[_Match]:
    kept: list[_Match] = []
    for match in sorted(matches, key=lambda m: -m.confidence):
        if not any(match.start < k.end and k.start < match.end for k in kept):
            kept.append(match)
    return sorted(kept, key=lambda m: m.start)


def _contextual(segment: Segment, match: _Match) -> float:
    confidence = match.confidence
    if not match.educational and reference_example(segment, match.start, match.end):
        confidence *= REFERENCE_FACTOR
    if match.category == APPROVAL_BAIT and segment.kind == "prose":
        confidence *= PROSE_BAIT_FACTOR
    return confidence


def _directive_hits(segment: Segment) -> tuple[list[Hit], bool]:
    matches, incomplete = _regex_matches(segment.text)
    hits = [
        Hit(segment, m.detector, m.pattern, m.category, _contextual(segment, m),
            segment.line_at(m.start), segment.text[m.start:m.end].strip(),
            _window(segment.text, m.start, m.end))
        for m in matches
    ]
    return hits, incomplete


def _unicode_confidence(kind: str, segment_kind: str) -> float:
    if kind == "bidi_control":
        return 1.0
    return 0.9 if segment_kind == "code" else 0.6


def _unicode_hits(segment: Segment) -> list[Hit]:
    grouped = suspicious_unicode(segment.text, bom_allowed=segment.line == 1)
    hits: list[Hit] = []
    for kind, found in grouped.items():
        first = found[0]
        detail = ", ".join(sorted({cp for h in found for cp in h.codepoints})) or first.text
        hits.append(Hit(segment, "unicode", kind, "hidden_unicode",
                        _unicode_confidence(kind, segment.kind), segment.line_at(first.start),
                        detail, _window(segment.text, first.start, first.end)))
    return hits


def _encoded_hits(segment: Segment) -> tuple[list[Hit], bool]:
    hits: list[Hit] = []
    incomplete = False
    for blob in find_encoded(segment.text):
        matches, timed_out = _regex_matches(blob.decoded)
        incomplete = incomplete or timed_out
        line = segment.line_at(blob.start)
        for m in matches:
            hits.append(Hit(segment, "encoded", f"{blob.encoding}:{m.pattern}", m.category,
                            m.confidence, line, blob.decoded[m.start:m.end].strip(),
                            _window(blob.decoded, m.start, m.end)))
        if first_bidi(blob.decoded) is not None:
            hits.append(Hit(segment, "encoded", f"{blob.encoding}:bidi_control",
                            "hidden_unicode", 1.0, line, "bidi control in decoded text",
                            blob.decoded[:2 * WINDOW_CHARS]))
    return hits, incomplete


def detect(segments: list[Segment]) -> tuple[list[Hit], bool]:
    """Return scored hits for all segments and whether any scan stopped early."""
    hits: list[Hit] = []
    incomplete = False
    for segment in segments:
        if segment.kind in DIRECTIVE_KINDS:
            found, timed_out = _directive_hits(segment)
            hits.extend(found)
            incomplete = incomplete or timed_out
        hits.extend(_unicode_hits(segment))
        encoded, timed_out = _encoded_hits(segment)
        hits.extend(encoded)
        incomplete = incomplete or timed_out
    return hits, incomplete
