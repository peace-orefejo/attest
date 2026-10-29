"""The headline comparison: a naive LLM judge and attest on the same answers."""

from __future__ import annotations

from functools import partial
from pathlib import Path

import typer
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from ...checks.judge_baseline import JudgeVerdict, naive_judge
from ...checks.verify import extract_claims, judge_trajectory, verify_claims
from ...core import CheckResult, Trajectory
from ...display.checks import header
from ...display.findings import findings_table
from ...display.theme import STYLES, badge, percent
from ..app import JSON_OPT, MODEL_OPT, PROVIDER_OPT, app
from ..common import emit_json, llm_ctx, load_trajectories, print_view, require_key

OUTCOMES = {
    (True, True): ("caught", "attest caught a false claim the LLM judge waved through."),
    (False, True): ("both_caught", "Both caught the problem."),
    (True, False): ("both_passed", "Both agree this answer is sound."),
    (False, False): ("judge_only", "The LLM judge flagged something attest's grounding didn't."),
}


def _outcome(verdict: JudgeVerdict, result: CheckResult) -> tuple[str, str]:
    return OUTCOMES[(verdict.passed, bool(result.failures))]


def _view(traj: Trajectory, verdict: JudgeVerdict, result: CheckResult) -> Group:
    rows = Table.grid(padding=(0, 2))
    rows.add_column(no_wrap=True, style=STYLES["head"])
    rows.add_column(no_wrap=True)
    rows.add_column(ratio=1)
    rows.add_row("answer", "", Text(traj.final_answer))
    rows.add_row("LLM judge", badge(verdict.passed), Text(verdict.reason, style=STYLES["muted"]))
    rows.add_row("attest", badge(not result.failures),
                 Text(f"grounding {percent(result.score)} · {result.summary}", style=STYLES["muted"]))
    parts: list[RenderableType] = [header(Text("TASK", style=STYLES["head"]), traj.task), Text(""), rows]
    if result.failures:
        parts += [Text(""), findings_table(result.failures, indent=2)]
    parts += [Text(""), Text(_outcome(verdict, result)[1], style=STYLES["label"])]
    return Group(*parts)


@app.command()
def demo(
    path: Path = typer.Argument(Path("examples/trajectory.json")),
    provider: str = PROVIDER_OPT,
    model: str = MODEL_OPT,
    json_output: bool = JSON_OPT,
) -> None:
    """Run the naive LLM-judge and attest side by side — the headline comparison."""
    require_key(provider)
    rows: list[tuple[Trajectory, JudgeVerdict, CheckResult]] = []
    with llm_ctx(provider, model):
        for traj in load_trajectories(path):
            verdict = naive_judge(traj)
            result = judge_trajectory(traj, partial(extract_claims, task=traj.task), verify_claims)
            rows.append((traj, verdict, result))
    if json_output:
        emit_json([
            {"task": traj.task, "answer": traj.final_answer,
             "judge": verdict.model_dump(mode="json"), "attest": result.model_dump(mode="json"),
             "outcome": _outcome(verdict, result)[0]}
            for traj, verdict, result in rows
        ])
        return
    parts: list[RenderableType] = []
    for position, row in enumerate(rows):
        if position:
            parts.append(Text(""))
        parts.append(_view(*row))
    print_view(*parts)
