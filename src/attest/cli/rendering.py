from __future__ import annotations

import json

import typer

from ..results import CheckResult, Finding, Severity
from .outcomes import RunOutcome, TaskReport, TaskResult


def emit_json(value: object) -> None:
    typer.echo(json.dumps(value, indent=2))


def task_heading(task: str) -> str:
    return f"- {task[:70]!r}"


def render_check(result: CheckResult, indent: str = "") -> None:
    score = f"{result.score:.0%}" if result.score is not None else "—"
    flag = "PASS" if result.passed else "FAIL"
    typer.echo(f"{indent}{result.check:13} {score:>4}  {flag}  {result.summary}")
    for finding in result.findings:
        if finding.severity is Severity.PASS:
            continue
        _render_finding(finding, indent)


def _render_finding(finding: Finding, indent: str) -> None:
    where = f" (step {finding.step})" if finding.step is not None else ""
    severity = finding.severity.value.upper()
    typer.echo(f"{indent}    {severity} {finding.verdict}{where}: {finding.subject}")
    if finding.reason:
        typer.echo(f"{indent}      {finding.reason}")


def render_task_results(results: list[TaskResult]) -> None:
    for item in results:
        typer.echo(task_heading(item.task))
        render_check(item.result, indent="  ")
        typer.echo("")


def render_task_report(item: TaskReport) -> None:
    flag = "PASS" if item.report.passed else "FAIL"
    typer.echo(task_heading(item.task))
    typer.echo(f"  {flag}  overall {item.report.overall_score:.0%}")
    for result in item.report.results:
        render_check(result, indent="  ")
    typer.echo("")


def render_run_summary(outcome: RunOutcome) -> None:
    mean = outcome.mean_overall_score
    if mean is not None:
        typer.echo(f"Mean overall score: {mean:.0%}")
    usage = outcome.usage
    typer.echo(f"Usage: {usage.calls} calls, {usage.tokens} tokens ({usage.cache_hits} cache hits)")
    if outcome.stopped:
        typer.echo(
            f"Stopped after {len(outcome.reports)}/{outcome.total} trajectories: {outcome.stopped}"
        )
