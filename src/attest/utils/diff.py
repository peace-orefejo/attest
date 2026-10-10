from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

LineKind = Literal["+", "-", " "]

_FILE_HEADER = re.compile(r"^\+\+\+ (?:b/)?(?P<path>\S+)")
_HUNK_HEADER = re.compile(r"^@@ -(?P<old>\d+)(?:,\d+)? \+(?P<new>\d+)(?:,\d+)? @@")


@dataclass(frozen=True)
class DiffLine:
    kind: LineKind
    text: str
    old_no: int | None
    new_no: int | None


@dataclass
class Hunk:
    header: str
    old_start: int
    new_start: int
    lines: list[DiffLine] = field(default_factory=list)

    def render(self) -> str:
        body = "\n".join(f"{line.kind}{line.text}" for line in self.lines)
        return f"{self.header}\n{body}" if body else self.header


@dataclass
class FileDiff:
    path: str
    hunks: list[Hunk] = field(default_factory=list)

    def added_lines(self) -> list[tuple[int, str]]:
        return [(line.new_no, line.text) for hunk in self.hunks for line in hunk.lines
                if line.kind == "+" and line.new_no is not None]

    def changed_line_count(self) -> int:
        return sum(1 for hunk in self.hunks for line in hunk.lines if line.kind != " ")


def parse_unified_diff(text: str, path: str | None = None) -> list[FileDiff]:
    files: list[FileDiff] = []
    current: FileDiff | None = None
    hunk: Hunk | None = None
    old_no = new_no = 0
    for raw in text.splitlines():
        header = _FILE_HEADER.match(raw)
        if header:
            current = FileDiff(path=header.group("path"))
            files.append(current)
            hunk = None
            continue
        if raw.startswith("--- ") or raw.startswith("diff --git") or raw.startswith("index "):
            continue
        hunk_header = _HUNK_HEADER.match(raw)
        if hunk_header:
            if current is None:
                current = FileDiff(path=path or "")
                files.append(current)
            old_no, new_no = int(hunk_header.group("old")), int(hunk_header.group("new"))
            hunk = Hunk(header=raw, old_start=old_no, new_start=new_no)
            current.hunks.append(hunk)
            continue
        if hunk is None or not raw or raw.startswith("\\"):
            continue
        kind, body = raw[0], raw[1:]
        if kind == "+":
            hunk.lines.append(DiffLine("+", body, None, new_no))
            new_no += 1
        elif kind == "-":
            hunk.lines.append(DiffLine("-", body, old_no, None))
            old_no += 1
        elif kind == " ":
            hunk.lines.append(DiffLine(" ", body, old_no, new_no))
            old_no += 1
            new_no += 1
    if path is not None:
        for file_diff in files:
            if not file_diff.path:
                file_diff.path = path
    return files


def cut_hunks(file_diff: FileDiff, max_chars: int) -> tuple[str, int]:
    kept: list[str] = []
    used = 0
    for index, hunk in enumerate(file_diff.hunks):
        rendered = hunk.render()
        if kept and used + len(rendered) > max_chars:
            return "\n".join(kept), len(file_diff.hunks) - index
        kept.append(rendered)
        used += len(rendered) + 1
    return "\n".join(kept), 0
