"""Small, linear-time helpers for reading markdown review guides."""

from __future__ import annotations

import re

_CODE_SPAN = re.compile(r"(`+)(.+?)\1")
_EMPHASIS = re.compile(r"(?<![\w*])(\*\*|__)(?=\S)(.+?)(?<=\S)\1(?![\w*])")
_SPACES = re.compile(r"\s+")
_COMMENT_OPEN = "<!--"
_COMMENT_CLOSE = "-->"


def strip_comments(markdown: str) -> str:
    """Remove HTML comments; an unclosed comment runs to the end of the text."""
    pieces: list[str] = []
    position = 0
    while True:
        start = markdown.find(_COMMENT_OPEN, position)
        if start < 0:
            pieces.append(markdown[position:])
            return "".join(pieces)
        pieces.append(markdown[position:start])
        end = markdown.find(_COMMENT_CLOSE, start + len(_COMMENT_OPEN))
        if end < 0:
            return "".join(pieces)
        position = end + len(_COMMENT_CLOSE)


def clean_inline(text: str) -> str:
    """Drop emphasis and code-span markers and collapse whitespace."""
    parts = _CODE_SPAN.split(text)
    pieces: list[str] = []
    for index in range(0, len(parts), 3):
        pieces.append(_EMPHASIS.sub(r"\2", parts[index]))
        if index + 2 < len(parts):
            pieces.append(parts[index + 2])
    return _SPACES.sub(" ", "".join(pieces)).strip()
