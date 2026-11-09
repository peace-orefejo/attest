from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field, computed_field

from ...llm import Reasoning
from ...results import CheckResult, Finding
from ..evidence import Omission
from ..guidelines import ReviewGuidelines
from ..models import GateMode, OutputType, ReviewOutput


class OutputDecision(BaseModel):
    index: int
    output_type: OutputType
    text: str = ""
    question: str | None = None
    line: int | None = None
    """For an issue: the line it is about, numbered in the new version of its file."""
    suggestion: str | None = None
    """For an issue on a line: the full corrected text of that line."""
    paths: list[str] = Field(default_factory=list[str])
    keep: bool
    mode: GateMode
    score: float | None = None
    summary: str = ""
    reasons: list[Finding] = Field(default_factory=list[Finding])
    notes: list[Finding] = Field(default_factory=list[Finding])
    omissions: list[Omission] = Field(default_factory=list[Omission])


class ReviewResult(BaseModel):
    decisions: list[OutputDecision]
    injection: CheckResult
    guidelines: ReviewGuidelines | None = None
    written: bool = False
    writer_failure: str | None = None
    """Why attest's own reviewer wrote nothing (a failed or cut-off call), or None. When set,
    there are no decisions: nothing was checked or kept."""
    warnings: list[str] = Field(default_factory=list[str])
    excluded_files: list[str] = Field(default_factory=list[str])
    reasoning: dict[str, Reasoning | None] = Field(default_factory=dict[str, Reasoning | None])
    """The reasoning level each call site was sent (writer, injection, guidelines and
    faithfulness), or None where the model takes no reasoning setting. Filled by
    `Attest.review()`."""
    outputs: list[ReviewOutput] = Field(default_factory=list[ReviewOutput], exclude=True)

    @computed_field
    @property
    def kept(self) -> list[int]:
        return [d.index for d in self.decisions if d.keep]

    @computed_field
    @property
    def dropped(self) -> list[int]:
        return [d.index for d in self.decisions if not d.keep]

    def filter(self, outputs: Sequence[ReviewOutput] | None = None) -> list[ReviewOutput]:
        """Return the outputs this review kept, in their original order."""
        if outputs is None:
            if not self.outputs and self.decisions:
                raise ValueError(
                    "This result carries no outputs (for example, it was loaded from JSON). "
                    "Pass the outputs to filter()."
                )
            outputs = self.outputs
        if len(outputs) != len(self.decisions):
            raise ValueError(f"Expected {len(self.decisions)} outputs, got {len(outputs)}.")
        return [outputs[i] for i in self.kept]
