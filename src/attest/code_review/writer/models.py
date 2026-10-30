from __future__ import annotations

from pydantic import BaseModel, Field


class WrittenIssue(BaseModel):
    file: str
    text: str


class WrittenSummary(BaseModel):
    file: str
    text: str


class WrittenReview(BaseModel):
    issues: list[WrittenIssue] = Field(default_factory=list[WrittenIssue])
    summaries: list[WrittenSummary] = Field(default_factory=list[WrittenSummary])
    overview: str = ""
