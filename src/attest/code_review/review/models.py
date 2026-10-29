from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field, computed_field

from ...core import CheckResult, Finding
from ..evidence import Omission
from ..guidelines import ReviewGuidelines
from ..models import GateMode, OutputType, ReviewOutput


class OutputDecision(BaseModel):
    index: int
    output_type: OutputType
    text: str = ""
    question: str | None = None
    paths: list[str] = Field(default_factory=list)
    keep: bool
    mode: GateMode
    score: float | None = None
    summary: str = ""
    reasons: list[Finding] = Field(default_factory=list)
    notes: list[Finding] = Field(default_factory=list)
    omissions: list[Omission] = Field(default_factory=list)


class ReviewResult(BaseModel):
    decisions: list[OutputDecision]
    injection: CheckResult
    guidelines: ReviewGuidelines | None = None
    written: bool = False
    warnings: list[str] = Field(default_factory=list)
    outputs: list[ReviewOutput] = Field(default_factory=list, exclude=True)

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
                raise ValueError("This result carries no outputs (for example, it was loaded from JSON). "
                                 "Pass the outputs to filter().")
            outputs = self.outputs
        if len(outputs) != len(self.decisions):
            raise ValueError(f"Expected {len(self.decisions)} outputs, got {len(outputs)}.")
        return [outputs[i] for i in self.kept]
