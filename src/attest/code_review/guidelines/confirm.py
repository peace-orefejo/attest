"""A second, narrow look at each reported break before it can drop an output."""

from __future__ import annotations

from pydantic import BaseModel

from ...core.llm import call
from ..models import ReviewOutput
from .models import Guideline
from .prompts import CONFIRM_PROMPT


class ConfirmOut(BaseModel):
    reports_code: bool = False
    approves_code: bool = False
    does_itself: bool = False
    reason: str = ""

    @property
    def breaks(self) -> bool:
        return self.approves_code or self.does_itself


def confirm_break(rule: Guideline, output: ReviewOutput, quote: str) -> ConfirmOut:
    """Ask whether the output itself breaks the rule, rather than describing code that does.

    The answer is split into three facts, and only approving such code or doing the forbidden
    thing counts as a break. Reporting code that breaks the rule never does.
    """
    user = (f"Rule {rule.id}: {rule.text}\n\nOutput type: {output.output_type}\n"
            f"Output:\n{output.text}\n\nWords said to break the rule:\n{quote}")
    return call(system=CONFIRM_PROMPT, user=user, output=ConfirmOut, max_tokens=512)
