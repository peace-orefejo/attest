"""Match paths against gitignore-style patterns: globs, `**`, directory patterns and `!`.

Each rule is matched against a path in one pass over the path's segments, and that pass gives
the rule's verdict for the path and for every one of its parent directories at once. So one
path costs at most (rules x pattern segments x path segments) single-segment glob matches,
however the patterns are written. Each glob is an `fnmatch` regex matched against one segment,
and a `**` is a running OR over offsets, so no pattern makes matching backtrack across
segments.

A floating path (see `PathParts`) is matched from every starting segment in that same pass,
with one bit per start offset.
"""

from __future__ import annotations

import fnmatch
import itertools
import re
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict

from .ignore_paths import normalize_path, split_path

__all__ = [
    "IgnoreRule",
    "is_ignored",
    "normalize_path",
    "parse_rule",
    "parse_rules",
    "parts_ignored",
]

Segment = re.Pattern[str] | None
"""One compiled path segment of a pattern; None stands for `**` (any number of segments)."""

_ANY_SEGMENT = re.compile(fnmatch.translate("*"))
_GLOB_SPECIALS = frozenset("*?[")


class IgnoreRule(BaseModel):
    """One parsed pattern line."""

    model_config = ConfigDict(frozen=True)

    pattern: str
    segments: tuple[Segment, ...]
    negated: bool = False
    directory_only: bool = False
    literal: str | None = None
    """One segment the pattern names exactly; a path without it can't match."""

    def ends(self, parts: Sequence[str], starts: int) -> list[int] | None:
        """For each end offset `j`, a bitmask of the start offsets `i` (chosen from `starts`)
        for which the rule matches `parts[i:j]`; None when it matches nowhere."""
        reach = [starts & (1 << index) for index in range(len(parts) + 1)]
        for segment in self.segments:
            if segment is None:
                reach = list(itertools.accumulate(reach, _either))
                continue
            reach = [0, *_advance(segment, reach, parts)]
            if not any(reach):
                return None
        return reach


def parse_rules(lines: Iterable[str]) -> list[IgnoreRule]:
    """Parse pattern lines, skipping blank lines and `#` comments."""
    return [rule for rule in (parse_rule(line) for line in lines) if rule is not None]


def parse_rule(line: str) -> IgnoreRule | None:
    """Parse one pattern line, or return None for a blank line or a comment."""
    text = _strip_trailing_spaces(line.rstrip("\r\n"))
    if not text or text.startswith("#"):
        return None
    negated = text.startswith("!")
    body = text[1:] if negated else text
    directory_only = body.endswith("/")
    body = body.rstrip("/")
    anchored = "/" in body
    pieces = [piece for piece in body.split("/") if piece]
    if not pieces:
        return None
    segments = _compile_segments(pieces, ends_inside=text.rstrip("/").endswith("/**"))
    if not anchored:
        segments = (None, *segments)
    return IgnoreRule(
        pattern=text,
        segments=segments,
        negated=negated,
        directory_only=directory_only,
        literal=next((piece for piece in reversed(pieces) if _is_literal(piece)), None),
    )


def is_ignored(path: str, rules: Sequence[IgnoreRule], *, is_dir: bool = False) -> bool:
    """True when the last rule matching the path, or one of its parent directories, ignores it.

    As in git, a file inside an ignored directory stays ignored even if a later `!` rule
    matches the file itself. The path is normalized first (see `split_path`), and a floating
    path is ignored when it would be from any one of its starting segments.
    """
    split = split_path(path)
    return parts_ignored(split.parts, rules, is_dir=is_dir, floating=split.floating)


def parts_ignored(
    parts: Sequence[str], rules: Sequence[IgnoreRule], *, is_dir: bool, floating: bool = False
) -> bool:
    """`is_ignored` for a path already split into segments."""
    count = len(parts)
    if not rules or not count:
        return False
    starts = (1 << count) - 1 if floating else 1
    before = [(1 << end) - 1 for end in range(count + 1)]
    decided = [0] * (count + 1)
    present = frozenset(parts)
    ignored = 0
    for rule in reversed(rules):
        if rule.literal is not None and rule.literal not in present:
            continue
        ends = rule.ends(parts, starts)
        if ends is None:
            continue
        last = count if is_dir or not rule.directory_only else count - 1
        for end in range(1, last + 1):
            fresh = ends[end] & before[end] & ~decided[end]
            if fresh:
                decided[end] |= fresh
                if not rule.negated:
                    ignored |= fresh
    return ignored != 0


def _either(seen: int, here: int) -> int:
    return seen | here


def _advance(segment: re.Pattern[str], reach: list[int], parts: Sequence[str]) -> list[int]:
    return [
        mask if mask and segment.match(part) is not None else 0
        for mask, part in zip(reach, parts, strict=False)
    ]


def _is_literal(piece: str) -> bool:
    return piece != "**" and not any(char in piece for char in "*?[\\")


def _compile_segments(pieces: list[str], *, ends_inside: bool) -> tuple[Segment, ...]:
    segments: list[Segment] = []
    for piece in pieces:
        if piece == "**":
            if not segments or segments[-1] is not None:
                segments.append(None)
            continue
        segments.append(re.compile(fnmatch.translate(_glob(piece))))
    if ends_inside and segments and segments[-1] is None:
        segments.insert(len(segments) - 1, _ANY_SEGMENT)
    return tuple(segments)


def _glob(piece: str) -> str:
    """Rewrite gitignore escapes and `[^...]` into the fnmatch syntax."""
    out: list[str] = []
    index = 0
    while index < len(piece):
        char = piece[index]
        if char == "\\" and index + 1 < len(piece):
            escaped = piece[index + 1]
            out.append(f"[{escaped}]" if escaped in _GLOB_SPECIALS else escaped)
            index += 2
            continue
        if char == "[" and piece.startswith("[^", index):
            out.append("[!")
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _strip_trailing_spaces(text: str) -> str:
    while text.endswith(" ") and not text.endswith("\\ "):
        text = text[:-1]
    return text
