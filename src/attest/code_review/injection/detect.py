"""Run the deterministic detectors over segments and score each hit."""

from __future__ import annotations

from collections import Counter

from ...checks.injection import (
    DEFAULT_DETECTORS,
    EncodedPayloadDetector,
    InjectionDetector,
    RegexDetector,
    UnicodeDetector,
)
from ...checks.injection.hidden_unicode import first_bidi
from ...checks.injection.matching import QUOTED_EXAMPLE_CONFIDENCE_FACTOR
from ...content import Detection, TextSegment
from ...utils.encoded_scan import MAX_BLOBS, find_encoded
from ...utils.json_types import JsonObject
from .context import (
    GENERIC_FACTOR,
    PROSE_BAIT_FACTOR,
    REFERENCE_FACTOR,
    is_reference_path,
    reference_example,
)
from .hits import WINDOW_CHARS, Hit, HitScan, Match, MatchScan, strongest, window
from .patterns import APPROVAL_BAIT, CODE_REVIEW_PATTERNS
from .segments import Segment
from .unicode_hits import unicode_hits

DIRECTIVE_KINDS = frozenset({"comment", "docstring", "string", "prose"})
MATCH_CAP = 20
_CODE_REVIEW = RegexDetector(CODE_REVIEW_PATTERNS, max_matches_per_pattern=MATCH_CAP)
_SCORED_HERE = (UnicodeDetector, EncodedPayloadDetector)


def detect(segments: list[Segment]) -> tuple[list[Hit], bool]:
    """Return scored hits for all segments and whether any scan stopped early."""
    hits: list[Hit] = []
    incomplete = False
    for segment in segments:
        if segment.kind in DIRECTIVE_KINDS:
            directive = _directive_hits(segment)
            hits.extend(directive.hits)
            incomplete = incomplete or directive.incomplete
        hits.extend(unicode_hits(segment))
        encoded = _encoded_hits(segment)
        hits.extend(encoded.hits)
        incomplete = incomplete or encoded.incomplete
    return hits, incomplete


def _directive_hits(segment: Segment) -> HitScan:
    scan = _regex_matches(segment.text)
    hits = [
        Hit(
            segment=segment,
            detector=m.detector,
            pattern=m.pattern,
            category=m.category,
            confidence=_contextual(segment, m),
            line=segment.line_at(m.start),
            evidence=segment.text[m.start : m.end].strip(),
            window=window(segment.text, m.start, m.end),
        )
        for m in scan.matches
    ]
    return HitScan(hits=hits, incomplete=scan.incomplete)


def _encoded_hits(segment: Segment) -> HitScan:
    hits: list[Hit] = []
    blobs = find_encoded(segment.text)
    incomplete = len(blobs) >= MAX_BLOBS or any(blob.truncated for blob in blobs)
    for blob in blobs:
        scan = _regex_matches(blob.decoded)
        incomplete = incomplete or scan.incomplete
        line = segment.line_at(blob.start)
        for m in scan.matches:
            hits.append(
                Hit(
                    segment=segment,
                    detector="encoded",
                    pattern=f"{blob.encoding}:{m.pattern}",
                    category=m.category,
                    confidence=m.confidence,
                    line=line,
                    evidence=blob.decoded[m.start : m.end].strip(),
                    window=window(blob.decoded, m.start, m.end),
                )
            )
        if first_bidi(blob.decoded) is not None:
            hits.append(
                Hit(
                    segment=segment,
                    detector="encoded",
                    pattern=f"{blob.encoding}:bidi_control",
                    category="hidden_unicode",
                    confidence=1.0,
                    line=line,
                    evidence="bidi control in decoded text",
                    window=blob.decoded[: 2 * WINDOW_CHARS],
                )
            )
    return HitScan(hits=hits, incomplete=incomplete)


def _regex_matches(text: str) -> MatchScan:
    segment = TextSegment(text=text, location="", source_kind="code_review", subject="")
    sources: list[tuple[str, InjectionDetector]] = [
        ("regex", d) for d in DEFAULT_DETECTORS if not isinstance(d, _SCORED_HERE)
    ]
    sources.append(("code_review", _CODE_REVIEW))
    matches: list[Match] = []
    incomplete = False
    for label, detector in sources:
        detections = detector.scan(segment)
        incomplete = incomplete or _stopped_early(detections)
        factor = GENERIC_FACTOR if label == "regex" else 1.0
        matches.extend(
            _match(label, detection, factor, len(text))
            for detection in detections
            if detection.verdict != "unscanned_content"
        )
    return MatchScan(matches=strongest(matches), incomplete=incomplete)


def _stopped_early(detections: list[Detection]) -> bool:
    if any(d.verdict == "unscanned_content" for d in detections):
        return True
    per_pattern = Counter(str(d.metadata.get("pattern", d.category)) for d in detections)
    return any(count >= MATCH_CAP for count in per_pattern.values())


def _match(label: str, detection: Detection, factor: float, length: int) -> Match:
    meta = detection.metadata
    educational = meta.get("quoted_educational_framing") is True
    confidence = detection.confidence
    if educational:
        confidence = min(1.0, confidence / QUOTED_EXAMPLE_CONFIDENCE_FACTOR)
    return Match(
        detector=label,
        pattern=str(meta.get("pattern", detection.category)),
        category=detection.category,
        confidence=confidence * factor,
        start=_int(meta, "char_start", 0),
        end=_int(meta, "char_end", length),
        educational=educational,
    )


def _contextual(segment: Segment, match: Match) -> float:
    confidence = match.confidence
    if match.educational and is_reference_path(segment.file):
        confidence *= QUOTED_EXAMPLE_CONFIDENCE_FACTOR
    elif reference_example(segment, match.start, match.end):
        confidence *= REFERENCE_FACTOR
    if match.category == APPROVAL_BAIT and segment.kind == "prose":
        confidence *= PROSE_BAIT_FACTOR
    return confidence


def _int(meta: JsonObject, key: str, default: int) -> int:
    value = meta.get(key)
    return value if isinstance(value, int) else default
