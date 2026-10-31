from __future__ import annotations

from pathlib import Path

import typer

from ...api import Attest
from ...llm import Budget
from ...scoring.report import DEFAULT_CHECKS, validate_evaluation_options
from ..context import require_key
from ..evaluation import EvaluationSettings, evaluate_all
from ..json_output import EXIT_BUDGET_EXCEEDED, RunData, emit, json_command
from ..loading import load_trajectories
from ..options import KIND_OPTION, MODEL_OPTION, PROVIDER_OPTION
from ..outcomes import RunOutcome


@json_command("run")
def run(
    path: Path,
    checks: str = typer.Option(
        ",".join(DEFAULT_CHECKS),
        "--checks",
        help="Comma-separated: faithfulness,tool_use,injection,role.",
    ),
    appropriate: bool = typer.Option(
        False, "--appropriate", help="Also run the LLM tool-choice check (1 call per tool call)."
    ),
    kind: str = KIND_OPTION,
    provider: str = PROVIDER_OPTION,
    model: str | None = MODEL_OPTION,
    max_calls: int | None = typer.Option(
        None, "--max-calls", help="Stop before exceeding this many judge calls."
    ),
    max_tokens: int | None = typer.Option(
        None, "--max-tokens", help="Stop before exceeding this many tokens."
    ),
    cache_dir: Path | None = typer.Option(
        None, "--cache-dir", help="Reuse judge verdicts from this directory across runs."
    ),
) -> None:
    """Full report on a trajectory (or JSONL): runs the chosen checks + an overall score."""
    selected = _selected_checks(checks, kind)
    require_key(provider)
    trajectories = load_trajectories(path)

    judge = Attest(
        provider=provider,
        model=model,
        budget=_budget(max_calls, max_tokens),
        cache=cache_dir or False,
    )
    settings = EvaluationSettings(checks=selected, appropriate=appropriate, kind=kind)
    outcome = evaluate_all(judge, trajectories, settings)

    emit("run", _run_data(outcome))
    if outcome.stopped:
        raise typer.Exit(code=EXIT_BUDGET_EXCEEDED)


def _selected_checks(checks: str, kind: str) -> list[str]:
    selected = [c.strip() for c in checks.split(",") if c.strip()]
    try:
        validate_evaluation_options(selected, kind)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    return selected


def _run_data(outcome: RunOutcome) -> RunData:
    return RunData(
        trajectories=outcome.reports,
        total=outcome.total,
        evaluated=len(outcome.reports),
        passed=sum(item.report.passed for item in outcome.reports),
        mean_overall_score=outcome.mean_overall_score,
        usage=outcome.usage,
        budget_exceeded=outcome.stopped,
    )


def _budget(max_calls: int | None, max_tokens: int | None) -> Budget | None:
    if not (max_calls or max_tokens):
        return None
    return Budget(max_calls=max_calls, max_tokens=max_tokens)
