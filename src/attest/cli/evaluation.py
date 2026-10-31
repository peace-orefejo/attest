from __future__ import annotations

from pydantic import BaseModel

from ..api import Attest
from ..checks.verify import MAX_CLAIMS
from ..llm import BudgetExceeded
from ..trajectory import Trajectory
from .outcomes import RunOutcome, TaskReport


class EvaluationSettings(BaseModel):
    checks: list[str]
    appropriate: bool
    kind: str
    max_claims: int = MAX_CLAIMS


def evaluate_all(
    judge: Attest,
    trajectories: list[Trajectory],
    settings: EvaluationSettings,
) -> RunOutcome:
    reports: list[TaskReport] = []
    stopped: str | None = None
    for traj in trajectories:
        try:
            item = _evaluate_one(judge, traj, settings)
        except BudgetExceeded as exc:
            stopped = str(exc)
            break
        reports.append(item)
    return RunOutcome(
        reports=reports, total=len(trajectories), usage=judge.usage.model_copy(), stopped=stopped
    )


def _evaluate_one(judge: Attest, traj: Trajectory, settings: EvaluationSettings) -> TaskReport:
    report = judge.evaluate(
        traj,
        checks=settings.checks,
        appropriate=settings.appropriate,
        answer_kind=settings.kind,
        max_claims=settings.max_claims,
    )
    return TaskReport(task=traj.task, report=report)
