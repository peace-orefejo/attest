from __future__ import annotations

from functools import partial
from pathlib import Path

import typer

from ...checks.claim_findings import is_unchecked
from ...checks.judge_baseline import JudgeVerdict, naive_judge
from ...checks.verify import extract_claims, judge_trajectory, verify_claims
from ...llm import BudgetExceeded, ProviderConfigError
from ...results import CheckResult
from ...trajectory import Trajectory
from ...utils.failures import failure_reason
from ..context import llm_context, require_key
from ..json_output import DemoComparison, DemoData, DemoOutcome, emit, json_command
from ..loading import load_trajectories
from ..options import MODEL_OPTION, PROVIDER_OPTION, REASONING_OPTION, require_reasoning

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
    reasoning: str = REASONING_OPTION,
) -> None:
    """Run the naive LLM-judge and attest side by side — the headline comparison.

    A naive judge call that fails or is cut off is reported as an unchecked judge, and an
    answer attest couldn't fully check (and found nothing wrong with) as inconclusive, never
    as passed.
    """
    policy = require_reasoning(reasoning)
    require_key(provider)
    with llm_context(provider, model, reasoning=policy):
        comparisons = [_compare(traj) for traj in load_trajectories(path)]
    emit("demo", DemoData(comparisons=comparisons))


def _compare(traj: Trajectory) -> DemoComparison:
    verdict, judge_error = _judge(traj)
    result = judge_trajectory(traj, partial(extract_claims, task=traj.task), verify_claims)
    return DemoComparison(
        task=traj.task,
        answer=traj.final_answer,
        judge=verdict,
        judge_error=judge_error,
        attest=result,
        outcome=_outcome(verdict, result),
    )


def _judge(traj: Trajectory) -> tuple[JudgeVerdict | None, str | None]:
    try:
        return naive_judge(traj), None
    except (BudgetExceeded, ProviderConfigError):
        raise
    except Exception as error:
        return None, failure_reason("The naive judge", error)


def _outcome(verdict: JudgeVerdict | None, result: CheckResult) -> DemoOutcome:
    if verdict is None:
        return "judge_unchecked"
    caught = bool(result.failures)
    if not caught and any(is_unchecked(f) for f in result.findings):
        return "inconclusive"
    return _OUTCOMES[(verdict.passed, caught)]
