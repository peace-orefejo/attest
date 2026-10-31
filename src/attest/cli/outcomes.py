from __future__ import annotations

from pydantic import BaseModel

from ..llm import Usage
from ..results import CheckResult, Report


class TaskResult(BaseModel):
    task: str
    result: CheckResult


class TaskReport(BaseModel):
    task: str
    report: Report


class RunOutcome(BaseModel):
    reports: list[TaskReport]
    total: int
    usage: Usage
    stopped: str | None = None

    @property
    def mean_overall_score(self) -> float | None:
        scores = [r.report.overall_score for r in self.reports]
        scored = [score for score in scores if score is not None]
        return sum(scored) / len(scored) if scored else None
