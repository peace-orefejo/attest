from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..results import Finding
from ..utils.json_types import JsonObject

OutputType = Literal["issue", "diff_summary", "group_summary", "canvas_answer"]
GateMode = Literal["lenient", "strict"]
InjectionVerdict = Literal["clean", "suspicious", "payload", "compromised"]

OUTPUT_TYPES: tuple[OutputType, ...] = ("issue", "diff_summary", "group_summary", "canvas_answer")
GATE_MODES: tuple[GateMode, ...] = ("lenient", "strict")
INJECTION_VERDICTS: tuple[InjectionVerdict, ...] = ("clean", "suspicious", "payload", "compromised")


class FileRead(BaseModel):
    tool: Literal["read_file", "grep"] = "read_file"
    arguments: JsonObject = Field(default_factory=dict)
    output: str


class ReviewOutput(BaseModel):
    output_type: OutputType
    text: str
    diffs: dict[str, str] = Field(default_factory=dict[str, str])
    changed_files: list[str] | None = None
    reads: list[FileRead] = Field(default_factory=list[FileRead])
    question: str | None = None
    group_name: str | None = None

    def paths(self) -> list[str]:
        seen: list[str] = list(self.diffs)
        for read in self.reads:
            path = read.arguments.get("path")
            if isinstance(path, str) and path not in seen:
                seen.append(path)
        return seen


class PullRequest(BaseModel):
    diffs: dict[str, str] = Field(default_factory=dict[str, str])
    changed_files: list[str] = Field(default_factory=list[str])
    title: str = ""
    description: str = ""
    commit_messages: list[str] = Field(default_factory=list[str])


class GateDecision(BaseModel):
    keep: bool
    mode: GateMode
    reasons: list[Finding] = Field(default_factory=list[Finding])
    notes: list[Finding] = Field(default_factory=list[Finding])
