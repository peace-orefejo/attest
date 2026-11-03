"""Swap the contents of files the user excluded for one-line notes, wherever they appear."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ...exclusions import EXCLUDED_REASON, Exclusions, excluded_note
from ..models import PullRequest, ReviewOutput
from .excluded_reads import GREP_WITHHELD, HiddenRead, hide_read
from .models import Omission, RenderedDiff

__all__ = [
    "GREP_WITHHELD",
    "HiddenOutput",
    "HiddenPullRequest",
    "HiddenRead",
    "changed_files_listing",
    "diff_excluded",
    "excluded_diff",
    "hide_output",
    "hide_pull_request",
    "hide_read",
    "without_excluded_diffs",
]

_GIT_HEADER = "diff --git "
_FILE_HEADERS = ("rename from ", "rename to ", "copy from ", "copy to ")
_DIFF_SIDES = ("a/", "b/")


class HiddenOutput(BaseModel):
    output: ReviewOutput
    excluded: list[str] = Field(default_factory=list[str])


class HiddenPullRequest(BaseModel):
    pr: PullRequest
    excluded: list[str] = Field(default_factory=list[str])


def excluded_diff(path: str) -> RenderedDiff:
    """The note that stands in for an excluded file's diff."""
    return RenderedDiff(
        path=path, text=excluded_note(path), omission=Omission(path=path, reason="excluded")
    )


def diff_excluded(path: str, text: str, exclusions: Exclusions) -> bool:
    """True when a diff's key, or any file its header lines name, is excluded.

    Each diff should be keyed by one repo-relative file, but a key with an `a/` or `b/` side
    prefix, several files' diffs under one key, or a rename out of an excluded file still
    fail closed: the whole diff is hidden. Header lines are `diff --git`, `rename` and
    `copy` lines, and `---`/`+++` pairs directly followed by a hunk header.
    """
    if not exclusions.active:
        return False
    if text == excluded_note(path):
        return True
    return any(exclusions.excludes(name) for name in _diff_names(path, text))


def changed_files_listing(paths: list[str], exclusions: Exclusions | None) -> list[str]:
    """The changed-file list, marking each excluded path; the list itself stays complete."""
    if exclusions is None:
        return list(paths)
    return [f"{p} ({EXCLUDED_REASON})" if exclusions.excludes(p) else p for p in paths]


def hide_pull_request(pr: PullRequest, exclusions: Exclusions) -> HiddenPullRequest:
    """The pull request with each excluded file's diff replaced by its note."""
    hidden = _excluded_diffs(pr.diffs, exclusions)
    excluded = _union(hidden, exclusions.excluded(pr.changed_files))
    if not excluded:
        return HiddenPullRequest(pr=pr)
    diffs = _swap_diffs(pr.diffs, hidden)
    return HiddenPullRequest(pr=pr.model_copy(update={"diffs": diffs}), excluded=excluded)


def without_excluded_diffs(pr: PullRequest, exclusions: Exclusions) -> PullRequest:
    """The pull request with excluded files' diffs removed, for the injection scan."""
    hidden = set(_excluded_diffs(pr.diffs, exclusions))
    diffs = {path: text for path, text in pr.diffs.items() if path not in hidden}
    return pr if len(diffs) == len(pr.diffs) else pr.model_copy(update={"diffs": diffs})


def hide_output(output: ReviewOutput, exclusions: Exclusions) -> HiddenOutput:
    """The output with excluded diffs and reads replaced by notes."""
    if not exclusions.active:
        return HiddenOutput(output=output)
    reads = [hide_read(read, exclusions) for read in output.reads]
    hidden = _excluded_diffs(output.diffs, exclusions)
    excluded = _union(
        hidden,
        exclusions.excluded(output.changed_files or []),
        *(read.excluded for read in reads),
    )
    if not excluded:
        return HiddenOutput(output=output)
    diffs = _swap_diffs(output.diffs, hidden)
    updated = output.model_copy(update={"diffs": diffs, "reads": [read.read for read in reads]})
    return HiddenOutput(output=updated, excluded=excluded)


def _excluded_diffs(diffs: dict[str, str], exclusions: Exclusions) -> list[str]:
    return [path for path, text in diffs.items() if diff_excluded(path, text, exclusions)]


def _swap_diffs(diffs: dict[str, str], hidden: list[str]) -> dict[str, str]:
    return {path: excluded_note(path) if path in hidden else text for path, text in diffs.items()}


def _diff_names(path: str, text: str) -> list[str]:
    names = [path]
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(_GIT_HEADER):
            rest = line[len(_GIT_HEADER) :]
            names.extend([rest, *rest.split(" ")])
        elif line.startswith(_FILE_HEADERS):
            names.append(line.split(" ", 2)[-1])
        elif _is_file_header(lines, index):
            names.extend([_header_name(line), _header_name(lines[index + 1])])
    return list(dict.fromkeys(name for found in names for name in _with_and_without_side(found)))


def _is_file_header(lines: list[str], index: int) -> bool:
    """A `---` line, then `+++`, then a hunk header: no run of content lines looks like that."""
    following = lines[index + 1 : index + 3]
    return (
        lines[index].startswith("--- ")
        and len(following) == 2
        and following[0].startswith("+++ ")
        and following[1].startswith("@@")
    )


def _header_name(line: str) -> str:
    return line[4:].split("\t", 1)[0]


def _with_and_without_side(name: str) -> list[str]:
    stripped = name.strip().strip('"')
    if stripped.startswith(_DIFF_SIDES):
        return [stripped, stripped[2:]]
    return [stripped] if stripped and stripped != "/dev/null" else []


def _union(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(path for group in groups for path in group))
