"""Hidden-Unicode hits for one segment, one per kind of character found."""

from __future__ import annotations

from ...checks.injection.hidden_unicode import suspicious_unicode
from .hits import Hit, window
from .segments import Segment


def unicode_hits(segment: Segment) -> list[Hit]:
    grouped = suspicious_unicode(segment.text, bom_allowed=segment.line == 1)
    hits: list[Hit] = []
    for kind, found in grouped.items():
        first = found[0]
        detail = ", ".join(sorted({cp for h in found for cp in h.codepoints})) or first.text
        hits.append(
            Hit(
                segment=segment,
                detector="unicode",
                pattern=kind,
                category="hidden_unicode",
                confidence=_confidence(kind, segment.kind),
                line=segment.line_at(first.start),
                evidence=detail,
                window=window(segment.text, first.start, first.end),
            )
        )
    return hits


def _confidence(kind: str, segment_kind: str) -> float:
    if kind == "bidi_control":
        return 1.0
    return 0.9 if segment_kind == "code" else 0.6
