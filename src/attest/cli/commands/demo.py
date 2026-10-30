from __future__ import annotations

from functools import partial
from pathlib import Path

import typer

from ...checks.judge_baseline import naive_judge
from ...checks.verify import extract_claims, judge_trajectory, verify_claims
from ...trajectory import Trajectory
from ..context import llm_context, require_key
from ..demo_view import DemoRow, demo_view
from ..loading import load_trajectories
from ..options import JSON_OPTION, MODEL_OPTION, PROVIDER_OPTION
from ..rendering import emit_json, print_blocks


def demo(
    path: Path = typer.Argument(Path("examples/trajectory.json")),
    provider: str = PROVIDER_OPTION,
    model: str | None = MODEL_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Run the naive LLM-judge and attest side by side — the headline comparison."""
    require_key(provider)
    with llm_context(provider, model):
        rows = [_compare(traj) for traj in load_trajectories(path)]
    if json_output:
        emit_json([row.to_json() for row in rows])
        return
    print_blocks([demo_view(row) for row in rows])


def _compare(traj: Trajectory) -> DemoRow:
    verdict = naive_judge(traj)
    result = judge_trajectory(traj, partial(extract_claims, task=traj.task), verify_claims)
    return DemoRow(trajectory=traj, verdict=verdict, result=result)
