from __future__ import annotations

from functools import partial
from pathlib import Path

import typer

from ...checks.judge_baseline import naive_judge
from ...checks.verify import extract_claims, judge_trajectory, verify_claims
from ...trajectory import Trajectory
from ..context import llm_context, require_key
from ..json_output import DemoComparison, DemoData, DemoOutcome, emit, json_command
from ..loading import load_trajectories
from ..options import MODEL_OPTION, PROVIDER_OPTION

_OUTCOMES: dict[tuple[bool, bool], DemoOutcome] = {
    (True, True): "caught",
    (False, True): "both_caught",
    (True, False): "both_passed",
    (False, False): "judge_only",
}


@json_command("demo")
def demo(
    path: Path = typer.Argument(Path("examples/trajectory.json")),
    provider: str = PROVIDER_OPTION,
    model: str | None = MODEL_OPTION,
) -> None:
    """Run the naive LLM-judge and attest side by side — the headline comparison."""
    require_key(provider)
    with llm_context(provider, model):
        comparisons = [_compare(traj) for traj in load_trajectories(path)]
    emit("demo", DemoData(comparisons=comparisons))


def _compare(traj: Trajectory) -> DemoComparison:
    verdict = naive_judge(traj)
    result = judge_trajectory(traj, partial(extract_claims, task=traj.task), verify_claims)
    return DemoComparison(
        task=traj.task,
        answer=traj.final_answer,
        judge=verdict,
        attest=result,
        outcome=_OUTCOMES[(verdict.passed, bool(result.failures))],
    )
