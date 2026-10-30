from __future__ import annotations

from pydantic import BaseModel, Field

from ...results import Finding


class FindingSplit(BaseModel):
    """Findings that drop an output, and findings shown beside it that do not."""

    drops: list[Finding] = Field(default_factory=list[Finding])
    notes: list[Finding] = Field(default_factory=list[Finding])
