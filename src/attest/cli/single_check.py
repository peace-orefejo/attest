from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..results import CheckResult
from ..trajectory import Trajectory
from .json_output import CheckData, emit
from .loading import load_trajectories
from .outcomes import TaskResult

CheckFn = Callable[[Trajectory], CheckResult]


def run_single_check(command: str, path: Path, check: CheckFn) -> None:
    results = [TaskResult(task=traj.task, result=check(traj)) for traj in load_trajectories(path)]
    emit(command, CheckData(trajectories=results))
