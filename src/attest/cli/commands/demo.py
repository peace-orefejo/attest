from __future__ import annotations

from pathlib import Path

import typer

from ...checks.judge_baseline import JudgeVerdict, naive_judge
from ...checks.verify import extract_claims, judge_trajectory, verify_claims
from ...results import CheckResult
from ...trajectory import Trajectory
from ..context import llm_context, require_key
from ..loading import load_trajectories
from ..options import MODEL_OPTION, PROVIDER_OPTION

_RULE = "-" * 72


def demo(
    path: Path = typer.Argument(Path("examples/trajectory.json")),
    provider: str = PROVIDER_OPTION,
    model: str | None = MODEL_OPTION,
) -> None:
    """Run the naive LLM-judge and attest side by side — the headline comparison."""
    require_key(provider)
    with llm_context(provider, model):
        for traj in load_trajectories(path):
            _compare(traj)
    typer.echo(_RULE)


def _compare(traj: Trajectory) -> None:
    _render_task(traj)
    verdict = naive_judge(traj)
    _render_verdict(verdict)
    result = judge_trajectory(traj, extract_claims, verify_claims)
    _render_grounding(result)
    typer.echo("")
    typer.echo(_conclusion(judge_passed=verdict.passed, flagged=bool(result.failures)))


def _render_task(traj: Trajectory) -> None:
    typer.echo(_RULE)
    typer.echo(f"TASK: {traj.task}\n")
    typer.echo("Agent's answer (the initial LLM's claim):")
    typer.echo(f"  {traj.final_answer}\n")


def _render_verdict(verdict: JudgeVerdict) -> None:
    typer.echo("Naive LLM-judge (reads the agent's reasoning):")
    typer.echo(f"  {'PASS' if verdict.passed else 'FAIL'} - {verdict.reason}\n")


def _render_grounding(result: CheckResult) -> None:
    typer.echo("attest (checks claims against real tool outputs only):")
    typer.echo(f"  grounding {_percent(result.score)}  ({result.summary})")
    for finding in result.failures:
        typer.echo(f"    UNSUPPORTED: {finding.subject}")
        if finding.reason:
            typer.echo(f"      {finding.reason}")


def _percent(score: float | None) -> str:
    return "—" if score is None else f"{score:.0%}"


def _conclusion(*, judge_passed: bool, flagged: bool) -> str:
    if judge_passed and flagged:
        return "=> attest caught a false claim the LLM-judge waved through."
    if flagged:
        return "=> both caught the problem."
    if judge_passed:
        return "=> both agree this answer is sound."
    return "=> the LLM-judge flagged something attest's grounding didn't."
