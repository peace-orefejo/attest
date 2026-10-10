"""Find hidden or deceptive Unicode: bidi controls, invisible characters, mixed-script words."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

UnicodeKind = Literal["bidi_control", "invisible", "mixed_script"]

BIDI_CONTROLS = frozenset(
    [chr(c) for c in range(0x202A, 0x202F)] + [chr(c) for c in range(0x2066, 0x206A)]
)
INVISIBLE = frozenset(["​", "‌", "‍", "⁠", "﻿"])

_WORD = re.compile(r"\w+")
_SCRIPTS = ("LATIN", "CYRILLIC", "GREEK")


@dataclass(frozen=True)
class UnicodeHit:
    kind: UnicodeKind
    start: int
    end: int
    text: str

    @property
    def codepoints(self) -> list[str]:
        return [f"U+{ord(ch):04X}" for ch in self.text if ch in BIDI_CONTROLS | INVISIBLE]


def _script(ch: str) -> str | None:
    name = unicodedata.name(ch, "")
    return next((script for script in _SCRIPTS if name.startswith(script + " ")), None)


def mixed_script(word: str) -> bool:
    """True when a word mixes Latin letters with Cyrillic or Greek letters."""
    scripts = {script for ch in word if (script := _script(ch))}
    return "LATIN" in scripts and bool(scripts & {"CYRILLIC", "GREEK"})


def scan_unicode(text: str) -> list[UnicodeHit]:
    """Return every bidi control, invisible character and mixed-script word in text."""
    hits: list[UnicodeHit] = []
    for index, ch in enumerate(text):
        if ch in BIDI_CONTROLS:
            hits.append(UnicodeHit("bidi_control", index, index + 1, ch))
        elif ch in INVISIBLE:
            hits.append(UnicodeHit("invisible", index, index + 1, ch))
    for match in _WORD.finditer(text):
        if mixed_script(match.group()):
            hits.append(UnicodeHit("mixed_script", match.start(), match.end(), match.group()))
    return sorted(hits, key=lambda hit: hit.start)
