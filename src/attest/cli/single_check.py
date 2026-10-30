from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..results import CheckResult
from ..trajectory import Trajectory
from .loading import load_trajectories
from .outcomes import TaskResult
from .rendering import emit_json, render_task_results

CheckFn = Callable[[Trajectory], CheckResult]


def run_single_check(path: Path, check: CheckFn, *, json_output: bool) -> None:
    results = [TaskResult(task=traj.task, result=check(traj)) for traj in load_trajectories(path)]
    if json_output:
        emit_json([item.to_json() for item in results])
        return
    render_task_results(results)
