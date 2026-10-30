from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OmissionReason = Literal["summarized", "generated", "truncated", "budget", "out_of_scope"]


class EvidenceLimits(BaseModel):
    """How many characters of diff one file, and one whole run, may put into evidence."""

    model_config = ConfigDict(frozen=True)

    max_file_chars: int = Field(default=12_000, gt=0)
    max_run_chars: int = Field(default=60_000, gt=0)


class Omission(BaseModel):
    """A file whose diff was summarized, cut or left out of the evidence, and why."""

    model_config = ConfigDict(frozen=True)

    path: str
    reason: OmissionReason
    changed_lines: int = 0
    omitted_hunks: int = 0


class RenderedDiff(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    text: str
    omission: Omission | None = None
