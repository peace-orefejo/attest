"""Hide recorded reads and greps that name files the user excluded, failing closed."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from pydantic import BaseModel, Field

from ...exclusions import (
    EXCLUDED_REASON,
    MAX_PATH_CHARS,
    Exclusions,
    cwd_roots,
    excluded_note,
    path_forms,
)
from ..models import FileRead
from .excluded_grep import MAX_GREP_CHECK_SEGMENTS, already_cut, cut_note, scan_grep

__all__ = ["GREP_WITHHELD", "MAX_GREP_CHECK_SEGMENTS", "HiddenRead", "hide_read", "notes"]

GREP_WITHHELD = f"[grep output withheld: it names files {EXCLUDED_REASON}]"
_SEARCH_TEXT_ARGUMENTS = frozenset({"pattern", "query", "regex"})
_LABEL_CHARS = 200


class HiddenRead(BaseModel):
    """A read with excluded content swapped for notes, and the excluded paths it named."""

    read: FileRead
    excluded: list[str] = Field(default_factory=list[str])
    named_only: list[str] = Field(default_factory=list[str])
    """Entries of `excluded` found in a grep line's text rather than its file name: the line
    may only mention an excluded file."""
    cut: bool = False
    """True when a grep was too long to check, so its unchecked lines were withheld."""


def hide_read(read: FileRead, exclusions: Exclusions) -> HiddenRead:
    """Hide a read that names an excluded file, failing closed.

    A read whose path-like arguments (any string or list of strings except the search text)
    name an excluded file or directory, as written or with symlinks resolved, becomes notes.
    An argument too long or with a line break, which can't be checked as a path, counts as
    excluded. A grep whose output names an excluded file anywhere, as a `path:` prefix, a
    heading line or a NUL-separated name, absolute or relative, is withheld whole, since its
    other lines may belong to that file. Checking a grep stops after `MAX_GREP_CHECK_SEGMENTS`
    path segments, and the lines after that point are withheld unchecked (`cut`).
    """
    if not exclusions.active:
        return HiddenRead(read=read)
    roots = cwd_roots()
    named = _excluded_arguments(read, exclusions, roots)
    if named:
        return HiddenRead(read=_with_output(read, notes(named)), excluded=named)
    if read.tool != "grep":
        return HiddenRead(read=read)
    scan = scan_grep(read.output, exclusions, roots)
    if scan.named:
        output = f"{notes(scan.named)}\n{GREP_WITHHELD}"
        return HiddenRead(
            read=_with_output(read, output), excluded=scan.named, named_only=scan.named_only
        )
    if scan.checked_lines is None:
        return HiddenRead(read=read, cut=already_cut(read.output))
    kept = read.output.splitlines()[: scan.checked_lines]
    output = "\n".join([*kept, cut_note(scan.checked_lines)])
    return HiddenRead(read=_with_output(read, output), cut=True)


def notes(paths: list[str]) -> str:
    """One note per excluded path, a line each."""
    return "\n".join(excluded_note(path) for path in paths)


def _excluded_arguments(read: FileRead, exclusions: Exclusions, roots: list[Path]) -> list[str]:
    named: list[str] = []
    for key, value in read.arguments.items():
        if key in _SEARCH_TEXT_ARGUMENTS:
            continue
        for item in _strings(value):
            if _uncheckable(item):
                named.append(_label(item))
            elif _excludes_file_or_directory(item, exclusions, roots):
                named.append(item)
    return list(dict.fromkeys(named))


def _strings(value: object) -> list[str]:
    """The non-empty strings in an argument value (a string or a list)."""
    items = cast("list[object]", value) if isinstance(value, list) else [value]
    return [item for item in items if isinstance(item, str) and item]


def _uncheckable(item: str) -> bool:
    return len(item) > MAX_PATH_CHARS or "\n" in item or "\r" in item


def _label(item: str) -> str:
    flat = item.replace("\r", "\\r").replace("\n", "\\n")
    if len(flat) <= _LABEL_CHARS:
        return flat
    return f"{flat[:_LABEL_CHARS]}... ({len(item)} characters)"


def _excludes_file_or_directory(path: str, exclusions: Exclusions, roots: list[Path]) -> bool:
    return any(
        exclusions.excludes(form) or exclusions.excludes(form, directory=True)
        for form in dict.fromkeys([path, *path_forms(path, roots)])
    )


def _with_output(read: FileRead, output: str) -> FileRead:
    return read.model_copy(update={"output": output})
