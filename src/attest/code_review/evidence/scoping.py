"""Which diffs and reads each review output type gets as evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models import FileRead, OutputType, ReviewOutput

DiffScope = Literal["all", "first"]


class ScopeRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    diffs: DiffScope
    reads: bool


RULES: dict[OutputType, ScopeRule] = {
    "issue": ScopeRule(diffs="all", reads=True),
    "diff_summary": ScopeRule(diffs="first", reads=False),
    "group_summary": ScopeRule(diffs="all", reads=False),
    "canvas_answer": ScopeRule(diffs="all", reads=True),
}


class Scope(BaseModel):
    """The evidence one output is checked against, and what was left out of it."""

    diffs: list[tuple[str, str]] = Field(default_factory=list[tuple[str, str]])
    reads: list[FileRead] = Field(default_factory=list[FileRead])
    changed_files: list[str] | None = None
    dropped_diffs: list[str] = Field(default_factory=list[str])
    dropped_reads: list[FileRead] = Field(default_factory=list[FileRead])


def scope_evidence(output: ReviewOutput) -> Scope:
    """Select the diffs, reads and changed-file list that an output is checked against."""
    rule = RULES[output.output_type]
    diffs = list(output.diffs.items())
    kept_diffs = diffs[:1] if rule.diffs == "first" else diffs
    changed = list(output.changed_files) if output.changed_files is not None else None
    return Scope(
        diffs=kept_diffs,
        reads=list(output.reads) if rule.reads else [],
        changed_files=changed,
        dropped_diffs=[path for path, _ in diffs[len(kept_diffs) :]],
        dropped_reads=[] if rule.reads else list(output.reads),
    )


def read_label(read: FileRead) -> str:
    """Name a recorded read by its path, its search pattern, or its tool."""
    for key in ("path", "pattern", "query"):
        value = read.arguments.get(key)
        if isinstance(value, str) and value:
            return value
    return read.tool
