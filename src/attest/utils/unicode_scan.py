"""Find hidden or deceptive Unicode: bidi controls, invisible characters, mixed-script words."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict

UnicodeKind = Literal["bidi_control", "invisible", "mixed_script"]

BIDI_CONTROLS = frozenset(
    [chr(c) for c in range(0x202A, 0x202F)] + [chr(c) for c in range(0x2066, 0x206A)]
)
TAG_CHARACTERS = frozenset(chr(c) for c in range(0xE0000, 0xE0080))
INVISIBLE = (
    frozenset(["\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\u180e"])
    | frozenset(chr(c) for c in range(0x2061, 0x2065))
    | TAG_CHARACTERS
)
HIDDEN = BIDI_CONTROLS | INVISIBLE

_WORD = re.compile(r"\w+")
_SCRIPTS = ("LATIN", "CYRILLIC", "GREEK")


class UnicodeHit(BaseModel):
    """One hidden character or mixed-script word, with its offsets in the scanned text."""

    model_config = ConfigDict(frozen=True)

    kind: UnicodeKind
    start: int
    end: int
    text: str

    @property
    def codepoints(self) -> list[str]:
        return [f"U+{ord(ch):04X}" for ch in self.text if ch in HIDDEN]


def mixed_script(word: str) -> bool:
    """True when a word mixes Latin letters with Cyrillic or Greek letters."""
    scripts = {script for ch in word if (script := _script(ch))}
    return "LATIN" in scripts and bool(scripts & {"CYRILLIC", "GREEK"})


def scan_unicode(text: str) -> list[UnicodeHit]:
    """Return every bidi control, invisible character and mixed-script word in text."""
    hits = [*_character_hits(text), *_mixed_script_hits(text)]
    return sorted(hits, key=lambda hit: hit.start)


def _character_hits(text: str) -> list[UnicodeHit]:
    hits: list[UnicodeHit] = []
    for index, ch in enumerate(text):
        if ch in BIDI_CONTROLS:
            hits.append(UnicodeHit(kind="bidi_control", start=index, end=index + 1, text=ch))
        elif ch in INVISIBLE:
            hits.append(UnicodeHit(kind="invisible", start=index, end=index + 1, text=ch))
    return hits


def _mixed_script_hits(text: str) -> list[UnicodeHit]:
    return [
        UnicodeHit(kind="mixed_script", start=match.start(), end=match.end(), text=match.group())
        for match in _WORD.finditer(text)
        if mixed_script(match.group())
    ]


def _script(ch: str) -> str | None:
    name = unicodedata.name(ch, "")
    return next((script for script in _SCRIPTS if name.startswith(script + " ")), None)
