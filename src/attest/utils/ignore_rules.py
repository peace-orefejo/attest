"""Match paths against gitignore-style patterns: globs, `**`, directory patterns and `!`.

Matching works one path segment at a time, so it takes time linear in the pattern and path
lengths whatever the pattern looks like: a hostile pattern can't make it backtrack.
"""

from __future__ import annotations

import fnmatch
import itertools
import re
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict

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

    def matches(self, parts: Sequence[str], *, is_dir: bool) -> bool:
        if self.directory_only and not is_dir:
            return False
        return _match_segments(self.segments, parts)


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
        pattern=text, segments=segments, negated=negated, directory_only=directory_only
    )


def is_ignored(path: str, rules: Sequence[IgnoreRule], *, is_dir: bool = False) -> bool:
    """True when the last rule matching the path, or one of its parent directories, ignores it.

    As in git, a file inside an ignored directory stays ignored even if a later `!` rule
    matches the file itself.
    """
    parts = normalize_path(path).split("/")
    if not rules or parts == [""]:
        return False
    for depth in range(1, len(parts)):
        if _last_verdict(parts[:depth], rules, is_dir=True):
            return True
    return bool(_last_verdict(parts, rules, is_dir=is_dir))


def normalize_path(path: str) -> str:
    """Use forward slashes and drop leading `/`, `./` and empty segments."""
    parts = path.replace("\\", "/").split("/")
    return "/".join(part for part in parts if part not in ("", "."))


def _last_verdict(
    parts: Sequence[str], rules: Sequence[IgnoreRule], *, is_dir: bool
) -> bool | None:
    for rule in reversed(rules):
        if rule.matches(parts, is_dir=is_dir):
            return not rule.negated
    return None


def _match_segments(segments: Sequence[Segment], parts: Sequence[str]) -> bool:
    reachable: list[bool] = [True] + [False] * len(parts)
    for segment in segments:
        if segment is None:
            reachable = list(itertools.accumulate(reachable, _either))
            continue
        reachable = [False] + [
            reachable[index] and segment.match(part) is not None for index, part in enumerate(parts)
        ]
    return reachable[-1]


def _either(seen: bool, here: bool) -> bool:
    return seen or here


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
