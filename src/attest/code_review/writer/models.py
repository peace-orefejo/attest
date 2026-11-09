from __future__ import annotations

from pydantic import BaseModel, Field


class WrittenIssue(BaseModel):
    file: str
    text: str
    line: int | None = None
    """The line the issue is about, numbered in the new version of the file, or None."""
    suggestion: str | None = None
    """The full replacement text for that one line, when the fix is that small, or None."""


class WrittenSummary(BaseModel):
    file: str
    text: str


class WrittenReview(BaseModel):
    issues: list[WrittenIssue] = Field(default_factory=list[WrittenIssue])
    summaries: list[WrittenSummary] = Field(default_factory=list[WrittenSummary])
    overview: str = ""


class Understanding(BaseModel):
    """Step 1: what each changed file now does."""

    summaries: list[WrittenSummary] = Field(default_factory=list[WrittenSummary])


class Design(BaseModel):
    """Step 2: what the change does as a whole, and how well the approach holds up."""

    overview: str = ""


class Findings(BaseModel):
    """Step 3: the problems the change introduces."""

    issues: list[WrittenIssue] = Field(default_factory=list[WrittenIssue])
