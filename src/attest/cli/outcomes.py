from __future__ import annotations

from pydantic import BaseModel

from ..llm import Usage
from ..results import CheckResult, Report
from ..utils.json_types import JsonObject


class TaskResult(BaseModel):
    task: str
    result: CheckResult

    def to_json(self) -> JsonObject:
        return {"task": self.task, "result": self.result.model_dump(mode="json")}


class TaskReport(BaseModel):
    task: str
    report: Report

    def to_json(self) -> JsonObject:
        return {"task": self.task, "report": self.report.model_dump(mode="json")}


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

    def to_json(self) -> JsonObject:
        return {
            "trajectories": [r.to_json() for r in self.reports],
            "mean_overall_score": self.mean_overall_score,
            "usage": self.usage.as_dict(),
            "budget_exceeded": self.stopped,
        }
