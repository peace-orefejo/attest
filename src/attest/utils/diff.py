"""Parse unified diffs into files, hunks and numbered lines, and cut hunks to a size."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

LineKind = Literal["+", "-", " "]

_FILE_HEADER = re.compile(r"^\+\+\+ (?:b/)?(?P<path>\S+)")
_HUNK_HEADER = re.compile(
    r"^@@ -(?P<old>\d+)(?:,(?P<old_len>\d+))? \+(?P<new>\d+)(?:,(?P<new_len>\d+))? @@"
)
_SKIPPED_HEADERS = ("--- ", "diff --git", "index ")


class DiffLine(BaseModel):
    kind: LineKind
    text: str
    old_no: int | None
    new_no: int | None


class Hunk(BaseModel):
    header: str
    old_start: int
    new_start: int
    lines: list[DiffLine] = Field(default_factory=list[DiffLine])

    def render(self) -> str:
        body = "\n".join(f"{line.kind}{line.text}" for line in self.lines)
        return f"{self.header}\n{body}" if body else self.header


class FileDiff(BaseModel):
    path: str
    hunks: list[Hunk] = Field(default_factory=list[Hunk])

    def added_lines(self) -> list[tuple[int, str]]:
        return [
            (line.new_no, line.text)
            for hunk in self.hunks
            for line in hunk.lines
            if line.kind == "+" and line.new_no is not None
        ]

    def changed_line_count(self) -> int:
        return sum(1 for hunk in self.hunks for line in hunk.lines if line.kind != " ")


class _Cursor(BaseModel):
    old_no: int = 0
    new_no: int = 0
    old_left: int = 0
    new_left: int = 0

    def inside(self) -> bool:
        return self.old_left > 0 or self.new_left > 0


def parse_unified_diff(text: str, path: str | None = None) -> list[FileDiff]:
    """Split a unified diff into files and hunks.

    Lines covered by a hunk header's counts are always hunk content, so added code that looks
    like a file header cannot end a hunk early and hide the lines after it.
    """
    files: list[FileDiff] = []
    current: FileDiff | None = None
    hunk: Hunk | None = None
    cursor = _Cursor()
    for raw in _lines(text):
        if hunk is not None and cursor.inside() and _is_content(raw):
            _add_line(hunk, cursor, raw or " ")
            continue
        header = _FILE_HEADER.match(raw)
        if header:
            current = FileDiff(path=header.group("path"))
            files.append(current)
            hunk = None
            continue
        if raw.startswith(_SKIPPED_HEADERS):
            continue
        hunk_header = _HUNK_HEADER.match(raw)
        if hunk_header:
            if current is None:
                current = FileDiff(path=path or "")
                files.append(current)
            hunk, cursor = _open_hunk(raw, hunk_header)
            current.hunks.append(hunk)
            continue
        if hunk is not None and raw:
            _add_line(hunk, cursor, raw)
    if path is not None:
        for file_diff in files:
            if not file_diff.path:
                file_diff.path = path
    return files


def cut_hunks(file_diff: FileDiff, max_chars: int) -> tuple[str, int]:
    """Render whole hunks until the next passes `max_chars`; return the text and hunks left out."""
    kept: list[str] = []
    used = 0
    for index, hunk in enumerate(file_diff.hunks):
        rendered = hunk.render()
        if kept and used + len(rendered) > max_chars:
            return "\n".join(kept), len(file_diff.hunks) - index
        kept.append(rendered)
        used += len(rendered) + 1
    return "\n".join(kept), 0


def _lines(text: str) -> list[str]:
    lines = text.split("\n")
    if lines and not lines[-1]:
        lines.pop()
    return [line.removesuffix("\r") for line in lines]


def _is_content(raw: str) -> bool:
    return not raw or raw[0] in "+- \\"


def _open_hunk(raw: str, match: re.Match[str]) -> tuple[Hunk, _Cursor]:
    old_no, new_no = int(match.group("old")), int(match.group("new"))
    cursor = _Cursor(
        old_no=old_no,
        new_no=new_no,
        old_left=_count(match.group("old_len")),
        new_left=_count(match.group("new_len")),
    )
    return Hunk(header=raw, old_start=old_no, new_start=new_no), cursor


def _count(value: str | None) -> int:
    return 1 if value is None else int(value)


def _add_line(hunk: Hunk, cursor: _Cursor, raw: str) -> None:
    kind, body = raw[0], raw[1:]
    if kind == "\\":
        return
    if kind == "+":
        hunk.lines.append(DiffLine(kind="+", text=body, old_no=None, new_no=cursor.new_no))
        cursor.new_no += 1
        cursor.new_left -= 1
    elif kind == "-":
        hunk.lines.append(DiffLine(kind="-", text=body, old_no=cursor.old_no, new_no=None))
        cursor.old_no += 1
        cursor.old_left -= 1
    elif kind == " ":
        hunk.lines.append(DiffLine(kind=" ", text=body, old_no=cursor.old_no, new_no=cursor.new_no))
        cursor.old_no += 1
        cursor.new_no += 1
        cursor.old_left -= 1
        cursor.new_left -= 1
