"""Swap the contents of files the user excluded for one-line notes, wherever they appear."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from ...exclusions import EXCLUDED_REASON, Exclusions, excluded_note
from ..models import FileRead, PullRequest, ReviewOutput
from .models import Omission, RenderedDiff

_GREP_SEPARATOR = re.compile(r":|-\d+-")
_MAX_GREP_SPLITS = 8


class HiddenRead(BaseModel):
    """A read with excluded content swapped for notes, and the excluded paths it named."""

    read: FileRead
    excluded: list[str] = Field(default_factory=list[str])


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


def changed_files_listing(paths: list[str], exclusions: Exclusions | None) -> list[str]:
    """The changed-file list, marking each excluded path; the list itself stays complete."""
    if exclusions is None:
        return list(paths)
    return [f"{p} ({EXCLUDED_REASON})" if exclusions.excludes(p) else p for p in paths]


def hide_pull_request(pr: PullRequest, exclusions: Exclusions) -> HiddenPullRequest:
    """The pull request with each excluded file's diff replaced by its note."""
    excluded = exclusions.excluded([*pr.diffs, *pr.changed_files])
    if not excluded:
        return HiddenPullRequest(pr=pr)
    diffs = {path: _hidden_diff(path, text, exclusions) for path, text in pr.diffs.items()}
    return HiddenPullRequest(pr=pr.model_copy(update={"diffs": diffs}), excluded=excluded)


def without_excluded_diffs(pr: PullRequest, exclusions: Exclusions) -> PullRequest:
    """The pull request with excluded files' diffs removed, for the injection scan."""
    diffs = {path: text for path, text in pr.diffs.items() if not exclusions.excludes(path)}
    return pr if len(diffs) == len(pr.diffs) else pr.model_copy(update={"diffs": diffs})


def hide_output(output: ReviewOutput, exclusions: Exclusions) -> HiddenOutput:
    """The output with excluded diffs and reads replaced by notes."""
    if not exclusions.active:
        return HiddenOutput(output=output)
    reads = [hide_read(read, exclusions) for read in output.reads]
    excluded = exclusions.excluded([*output.diffs, *(output.changed_files or [])])
    excluded += [path for read in reads for path in read.excluded if path not in excluded]
    if not excluded:
        return HiddenOutput(output=output)
    diffs = {path: _hidden_diff(path, text, exclusions) for path, text in output.diffs.items()}
    hidden = output.model_copy(update={"diffs": diffs, "reads": [read.read for read in reads]})
    return HiddenOutput(output=hidden, excluded=excluded)


def hide_read(read: FileRead, exclusions: Exclusions) -> HiddenRead:
    """A read of an excluded file becomes a note; a grep loses its excluded files' lines."""
    path = read.arguments.get("path")
    if isinstance(path, str) and _excludes_target(path, read, exclusions):
        return HiddenRead(read=_with_output(read, excluded_note(path)), excluded=[path])
    if read.tool != "grep":
        return HiddenRead(read=read)
    lines: list[str] = []
    excluded: list[str] = []
    for line in read.output.split("\n"):
        file = _grep_file(line, exclusions)
        if file is None:
            lines.append(line)
        elif file not in excluded:
            excluded.append(file)
            lines.append(excluded_note(file))
    if not excluded:
        return HiddenRead(read=read)
    return HiddenRead(read=_with_output(read, "\n".join(lines)), excluded=excluded)


def _excludes_target(path: str, read: FileRead, exclusions: Exclusions) -> bool:
    directory = read.tool == "grep" and exclusions.excludes(path, directory=True)
    return directory or exclusions.excludes(path)


def _grep_file(line: str, exclusions: Exclusions) -> str | None:
    for index, match in enumerate(_GREP_SEPARATOR.finditer(line)):
        if index >= _MAX_GREP_SPLITS:
            return None
        candidate = line[: match.start()]
        if candidate and exclusions.excludes(candidate):
            return candidate
    return None


def _hidden_diff(path: str, text: str, exclusions: Exclusions) -> str:
    return excluded_note(path) if exclusions.excludes(path) else text


def _with_output(read: FileRead, output: str) -> FileRead:
    return read.model_copy(update={"output": output})
