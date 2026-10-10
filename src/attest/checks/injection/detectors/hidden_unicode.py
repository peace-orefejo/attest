"""Rules for which hidden-Unicode hits matter, and how to show them safely."""

from __future__ import annotations

import unicodedata

from ....utils.unicode_scan import BIDI_CONTROLS, INVISIBLE, UnicodeHit, UnicodeKind, scan_unicode

BOM = "﻿"
JOINERS = frozenset({"‌", "‍"})
_JOINER_NEIGHBOURS = frozenset({"So", "Sk", "Mn", "Me", "Lo"})
_HIDDEN = BIDI_CONTROLS | INVISIBLE


def benign_unicode(text: str, hit: UnicodeHit, *, bom_allowed: bool = True) -> bool:
    """True for a leading BOM or a joiner beside an emoji or non-Latin letter."""
    if hit.text == BOM and hit.start == 0 and bom_allowed:
        return True
    if hit.text in JOINERS:
        neighbours = text[max(0, hit.start - 1):hit.start] + text[hit.end:hit.end + 1]
        return any(unicodedata.category(ch) in _JOINER_NEIGHBOURS for ch in neighbours)
    return False


def suspicious_unicode(
    text: str, *, bom_allowed: bool = True
) -> dict[UnicodeKind, list[UnicodeHit]]:
    """Non-benign hidden-Unicode hits grouped by kind, in order of first appearance."""
    grouped: dict[UnicodeKind, list[UnicodeHit]] = {}
    for hit in scan_unicode(text):
        if not benign_unicode(text, hit, bom_allowed=bom_allowed):
            grouped.setdefault(hit.kind, []).append(hit)
    return grouped


def first_bidi(text: str) -> int | None:
    """Offset of the first bidirectional control in text, or None."""
    return next((index for index, ch in enumerate(text) if ch in BIDI_CONTROLS), None)


def reveal(text: str) -> str:
    """Replace bidi controls and invisible characters with visible U+XXXX markers."""
    return "".join(f"<U+{ord(ch):04X}>" if ch in _HIDDEN else ch for ch in text)
