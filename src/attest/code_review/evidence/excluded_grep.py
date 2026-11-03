"""Find the excluded files a grep's output names, within a fixed checking budget."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from ...exclusions import MAX_PATH_CHARS, Exclusions, path_forms

MAX_GREP_CHECK_SEGMENTS = 50_000
"""How many path segments of candidate file names one grep's output may cost to check."""
_GREP_SEPARATOR = re.compile(r":|-\d+-|\x00")
_DRIVE = re.compile(r"[A-Za-z]:[\\/]")
_MAX_GREP_SPLITS = 8
_CUT_NOTE = re.compile(r"\[grep output cut after \d+ lines: ")


class GrepScan(BaseModel):
    named: list[str] = Field(default_factory=list[str])
    named_only: list[str] = Field(default_factory=list[str])
    """The entries of `named` found past a line's file name, which the line's text may only
    mention."""
    checked_lines: int | None = None
    """Set when the budget ran out: only this many lines were checked."""


def scan_grep(output: str, exclusions: Exclusions, roots: list[Path]) -> GrepScan:
    """The excluded files each line names, as written or with symlinks resolved.

    Each line's first candidate is its file name; a hit on a later candidate (a longer prefix,
    or the whole line) may come from the line's text naming an excluded file, so it is also
    listed in `named_only`.
    """
    verdicts: dict[str, bool] = {}
    named: list[str] = []
    named_only: list[str] = []
    budget = MAX_GREP_CHECK_SEGMENTS
    for number, line in enumerate(output.splitlines()):
        for index, candidate in enumerate(_grep_candidates(line)):
            if candidate not in verdicts:
                budget -= _segments(candidate)
                if budget < 0:
                    return GrepScan(
                        named=_unique(named), named_only=_unique(named_only), checked_lines=number
                    )
                verdicts[candidate] = _excluded(candidate, exclusions, roots)
            if verdicts[candidate]:
                named.append(candidate)
                if index > 0:
                    named_only.append(candidate)
                break
    return GrepScan(named=_unique(named), named_only=_unique(named_only))


def cut_note(lines: int) -> str:
    return (
        f"[grep output cut after {lines} lines: the rest was too long to check against the "
        "exclusion rules, so it was withheld]"
    )


def already_cut(output: str) -> bool:
    """True when the output ends with the note `cut_note` leaves."""
    lines = output.splitlines()
    return bool(lines) and _CUT_NOTE.match(lines[-1]) is not None


def _excluded(candidate: str, exclusions: Exclusions, roots: list[Path]) -> bool:
    if exclusions.excludes(candidate):
        return True
    forms = path_forms(candidate, roots)
    return any(exclusions.excludes(form) for form in forms if form != candidate)


def _grep_candidates(line: str) -> list[str]:
    """Each prefix of a grep line that could name its file, then the whole line (a heading).

    A Windows drive's colon (`C:\\`) is not a separator. A candidate deeper than any real path
    is kept, and the exclusion rules always exclude it, failing closed.
    """
    candidates: list[str] = []
    splits = 0
    for match in _GREP_SEPARATOR.finditer(line, 0, MAX_PATH_CHARS + 1):
        if match.start() == 1 and _DRIVE.match(line):
            continue
        if splits >= _MAX_GREP_SPLITS:
            break
        splits += 1
        candidates.append(line[: match.start()])
    if len(line) <= MAX_PATH_CHARS:
        candidates.append(line)
    return [candidate for candidate in candidates if candidate.strip()]


def _segments(path: str) -> int:
    return path.count("/") + path.count("\\") + 1


def _unique(paths: list[str]) -> list[str]:
    return list(dict.fromkeys(paths))
