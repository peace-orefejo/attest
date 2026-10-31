"""What happens because of a finding: the policy that maps findings to pass, review or block."""

from __future__ import annotations

import warnings
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..results import Disposition

Threshold = Annotated[float, Field(ge=0.0, le=1.0)]


class ToolUsePolicy(BaseModel):
    """Dispositions for tool-use findings.

    `on_invalid_arguments` is deprecated: no check reports invalid arguments yet, so setting it
    has no effect. It will be removed in a future minor release.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    on_disallowed_tool: Disposition = "block"
    on_unhandled_error: Disposition = "review"
    on_claimed_success: Disposition = "block"
    on_unnecessary_call: Disposition = "review"
    on_invalid_arguments: Disposition = "review"

    @model_validator(mode="after")
    def _warn_on_unused_option(self) -> Self:
        if "on_invalid_arguments" in self.model_fields_set:
            warnings.warn(
                "ToolUsePolicy.on_invalid_arguments has no effect: no check reports invalid "
                "arguments yet. It will be removed in a future minor release.",
                DeprecationWarning,
                stacklevel=2,
            )
        return self


class VerdictPolicy(BaseModel):
    """Decides each finding's disposition, and so the report's verdict.

    Checks report what happened; this policy decides what happens because of it. The
    report's verdict is the strictest disposition among its findings.

    `on_inconclusive_faithfulness` applies when a faithfulness result has claims but none could
    be checked against the evidence; it defaults to `review`, so an answer attest couldn't
    verify never reads as a pass. `on_injection_warning` applies to injection warnings
    (`suspicious`, `possible_injection`, `unscanned_content`); `compromised` always blocks.
    `min_score` maps a check name to the lowest acceptable score: below it, that check's
    passing findings become `review`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_use: ToolUsePolicy = ToolUsePolicy()
    on_inconclusive_faithfulness: Disposition = "review"
    on_injection_warning: Disposition = "pass"
    min_score: dict[str, Threshold] = Field(default_factory=dict[str, Threshold])
