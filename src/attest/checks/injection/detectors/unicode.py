"""Detection of bidi controls, invisible characters, and mixed-script words."""

from __future__ import annotations

from ....core import Detection, TextSegment
from ....utils.unicode_scan import UnicodeHit, UnicodeKind
from ..constants import POSSIBLE_INJECTION_THRESHOLD
from .hidden_unicode import reveal, suspicious_unicode

BIDI_CONFIDENCE = 1.0
LOW_SIGNAL_CONFIDENCE = 0.6
MAX_SPANS = 20


class UnicodeDetector:
    """Hidden or deceptive Unicode in untrusted text, one detection per kind per segment."""

    name = "unicode"

    def __init__(
        self,
        *,
        bidi_confidence: float = BIDI_CONFIDENCE,
        low_signal_confidence: float = LOW_SIGNAL_CONFIDENCE,
        possible_threshold: float = POSSIBLE_INJECTION_THRESHOLD,
        max_spans: int = MAX_SPANS,
    ) -> None:
        for label, value in (
            ("bidi_confidence", bidi_confidence),
            ("low_signal_confidence", low_signal_confidence),
            ("possible_threshold", possible_threshold),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{label} must be 0..1.")
        if max_spans <= 0:
            raise ValueError("max_spans must be positive.")
        self._bidi_confidence = bidi_confidence
        self._low_signal_confidence = low_signal_confidence
        self._possible_threshold = possible_threshold
        self._max_spans = max_spans

    def scan(self, segment: TextSegment) -> list[Detection]:
        return [
            self._detection(segment, kind, hits)
            for kind, hits in suspicious_unicode(segment.text).items()
        ]

    def _detection(
        self, segment: TextSegment, kind: UnicodeKind, hits: list[UnicodeHit]
    ) -> Detection:
        base = self._bidi_confidence if kind == "bidi_control" else self._low_signal_confidence
        confidence = base * segment.extraction_confidence
        first = hits[0]
        start = max(0, first.start - 15)
        end = min(len(segment.text), first.end + 45)
        return Detection(
            verdict=("possible_injection"
                     if confidence < self._possible_threshold else "suspicious"),
            detector=self.name,
            category="hidden_unicode",
            matched_text=reveal(segment.text[start:end]).strip(),
            location=segment.location,
            subject=segment.subject,
            step=segment.step,
            confidence=confidence,
            metadata={
                **segment.metadata,
                "pattern": kind,
                "char_start": first.start,
                "char_end": first.end,
                "occurrences": len(hits),
                "spans": [[hit.start, hit.end] for hit in hits[:self._max_spans]],
                "codepoints": sorted({cp for hit in hits for cp in hit.codepoints}),
            },
        )
