"""Hide recorded reads and greps that name files the user excluded, failing closed."""

from __future__ import annotations

import re
from typing import cast

from pydantic import BaseModel, Field

from ...exclusions import (
    EXCLUDED_REASON,
    MAX_PATH_CHARS,
    MAX_PATH_DEPTH,
    Exclusions,
    excluded_note,
)
from ..models import FileRead

GREP_WITHHELD = f"[grep output withheld: it names files {EXCLUDED_REASON}]"
MAX_GREP_CHECK_SEGMENTS = 50_000
"""How many path segments of candidate file names one grep's output may cost to check."""
_GREP_SEPARATOR = re.compile(r":|-\d+-|\x00")
_MAX_GREP_SPLITS = 8
_SEARCH_TEXT_ARGUMENTS = frozenset({"pattern", "query", "regex"})


class _GrepScan(BaseModel):
    named: list[str] = Field(default_factory=list[str])
    checked_lines: int | None = None
    """Set when the budget ran out: only this many lines were checked."""


class HiddenRead(BaseModel):
    """A read with excluded content swapped for notes, and the excluded paths it named."""

    read: FileRead
    excluded: list[str] = Field(default_factory=list[str])


def hide_read(read: FileRead, exclusions: Exclusions) -> HiddenRead:
    """Hide a read that names an excluded file, failing closed.

    A read whose path-like arguments (any string or list of strings except the search text)
    name an excluded file or directory becomes notes. A grep whose output names an excluded
    file anywhere, as a `path:` prefix, a heading line or a NUL-separated name, absolute or
    relative, is withheld whole, since its other lines may belong to that file. Checking a
    grep stops after `MAX_GREP_CHECK_SEGMENTS` path segments, and the lines after that point
    are withheld unchecked.
    """
    if not exclusions.active:
        return HiddenRead(read=read)
    named = _excluded_arguments(read, exclusions)
    if named:
        return HiddenRead(read=_with_output(read, notes(named)), excluded=named)
    if read.tool != "grep":
        return HiddenRead(read=read)
    scan = _scan_grep(read.output, exclusions)
    if scan.named:
        output = f"{notes(scan.named)}\n{GREP_WITHHELD}"
        return HiddenRead(read=_with_output(read, output), excluded=scan.named)
    if scan.checked_lines is None:
        return HiddenRead(read=read)
    kept = read.output.splitlines()[: scan.checked_lines]
    cut = _cut_note(scan.checked_lines)
    return HiddenRead(read=_with_output(read, "\n".join([*kept, cut])))


def notes(paths: list[str]) -> str:
    """One note per excluded path, a line each."""
    return "\n".join(excluded_note(path) for path in paths)


def _excluded_arguments(read: FileRead, exclusions: Exclusions) -> list[str]:
    named: list[str] = []
    for key, value in read.arguments.items():
        if key in _SEARCH_TEXT_ARGUMENTS:
            continue
        for item in _path_like(value):
            if _excludes_file_or_directory(item, exclusions):
                named.append(item)
    return list(dict.fromkeys(named))


def _path_like(value: object) -> list[str]:
    """The strings in an argument value (a string or a list) that could be a path."""
    items = cast("list[object]", value) if isinstance(value, list) else [value]
    return [
        item
        for item in items
        if isinstance(item, str) and 0 < len(item) <= MAX_PATH_CHARS and "\n" not in item
    ]


def _excludes_file_or_directory(path: str, exclusions: Exclusions) -> bool:
    return exclusions.excludes(path) or exclusions.excludes(path, directory=True)


def _scan_grep(output: str, exclusions: Exclusions) -> _GrepScan:
    verdicts: dict[str, bool] = {}
    named: list[str] = []
    budget = MAX_GREP_CHECK_SEGMENTS
    for number, line in enumerate(output.splitlines()):
        for candidate in _grep_candidates(line):
            if candidate not in verdicts:
                budget -= _segments(candidate)
                if budget < 0:
                    return _GrepScan(named=_unique(named), checked_lines=number)
                verdicts[candidate] = exclusions.excludes(candidate)
            if verdicts[candidate]:
                named.append(candidate)
                break
    return _GrepScan(named=_unique(named))


def _segments(path: str) -> int:
    return path.count("/") + path.count("\\") + 1


def _unique(paths: list[str]) -> list[str]:
    return list(dict.fromkeys(paths))


def _cut_note(lines: int) -> str:
    return (
        f"[grep output cut after {lines} lines: the rest was too long to check against the "
        "exclusion rules, so it was withheld]"
    )


def _grep_candidates(line: str) -> list[str]:
    """Each prefix of a grep line that could name its file, then the whole line (a heading).

    A prefix longer or deeper than any real path is skipped as file content, not a name.
    """
    candidates: list[str] = []
    for index, match in enumerate(_GREP_SEPARATOR.finditer(line, 0, MAX_PATH_CHARS + 1)):
        if index >= _MAX_GREP_SPLITS:
            break
        candidates.append(line[: match.start()])
    if len(line) <= MAX_PATH_CHARS:
        candidates.append(line)
    return [
        candidate
        for candidate in candidates
        if candidate.strip() and _segments(candidate) <= MAX_PATH_DEPTH
    ]


def _with_output(read: FileRead, output: str) -> FileRead:
    return read.model_copy(update={"output": output})
