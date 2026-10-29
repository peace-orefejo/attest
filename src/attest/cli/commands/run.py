"""The full report command: every chosen check on every trajectory, plus an overall score."""

from __future__ import annotations

from pathlib import Path

import typer

from ...scoring.report import DEFAULT_CHECKS, evaluate, validate_evaluation_options
from ..app import JSON_OPT, MODEL_OPT, PROVIDER_OPT, app
from ..common import emit_json, llm_ctx, load_trajectories, print_results, require_key


@app.command()
def run(
    path: Path,
    checks: str = typer.Option(",".join(DEFAULT_CHECKS), "--checks",
                               help="Comma-separated: faithfulness,tool_use,injection,role."),
    appropriate: bool = typer.Option(False, "--appropriate",
                                     help="Also run the LLM tool-choice check (1 call per tool call)."),
    kind: str = typer.Option("factual", "--kind",
                             help="Answer type: 'factual' (default), 'plan' (judge fidelity to the plan), 'code' (judge against diffs and source), or 'auto' (pick factual or code from the evidence)."),
    provider: str = PROVIDER_OPT,
    model: str = MODEL_OPT,
    json_output: bool = JSON_OPT,
) -> None:
    """Full report on a trajectory (or JSONL): runs the chosen checks + an overall score."""
    selected = [c.strip() for c in checks.split(",") if c.strip()]
    try:
        validate_evaluation_options(selected, kind)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    require_key(provider)
    trajectories = load_trajectories(path)
    with llm_ctx(provider, model):
        reports = [(traj, evaluate(traj, checks=selected, appropriate=appropriate, answer_kind=kind))
                   for traj in trajectories]

    overalls = [report.overall_score for _, report in reports if report.overall_score is not None]
    mean = sum(overalls) / len(overalls) if overalls else None
    if json_output:
        emit_json({
            "trajectories": [
                {"task": traj.task, "report": report.model_dump(mode="json")}
                for traj, report in reports
            ],
            "mean_overall_score": mean,
        })
        return
    passed = sum(report.passed for _, report in reports)
    footer = None
    if len(reports) > 1 and mean is not None:
        footer = f"{passed}/{len(reports)} passed · mean overall {mean:.0%}"
    print_results([(traj.task, report) for traj, report in reports], footer)
