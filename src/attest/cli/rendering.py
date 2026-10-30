from __future__ import annotations

import json
from collections.abc import Sequence

import typer
from rich.console import Console, RenderableType
from rich.text import Text

from ..display import strip_trailing, view
from .outcomes import RunOutcome, TaskReport, TaskResult


def emit_json(value: object) -> None:
    typer.echo(json.dumps(value, indent=2))


def print_view(*renderables: RenderableType) -> None:
    out = Console(highlight=False)
    with out.capture() as captured:
        for renderable in renderables:
            out.print(renderable)
    typer.echo(strip_trailing(captured.get()), nl=False)


def print_blocks(blocks: Sequence[RenderableType], footer: Sequence[str] = ()) -> None:
    parts: list[RenderableType] = []
    for position, block in enumerate(blocks):
        if position:
            parts.append(Text(""))
        parts.append(block)
    if footer:
        parts.append(Text(""))
        parts += [Text(line, style="bold") for line in footer]
    print_view(*parts)


def render_task_results(results: Sequence[TaskResult]) -> None:
    print_blocks([view(item.result, title=item.task) for item in results])


class ReportPrinter:
    """Print each task report as it finishes, with a blank line between reports."""

    def __init__(self) -> None:
        self.printed = 0

    def __call__(self, item: TaskReport) -> None:
        blocks: list[RenderableType] = [Text("")] if self.printed else []
        print_view(*blocks, view(item.report, title=item.task))
        self.printed += 1


def render_run_summary(outcome: RunOutcome) -> None:
    print_blocks([], footer=_run_summary(outcome))


def _run_summary(outcome: RunOutcome) -> list[str]:
    lines: list[str] = []
    mean = outcome.mean_overall_score
    if len(outcome.reports) > 1 and mean is not None:
        passed = sum(item.report.passed for item in outcome.reports)
        lines.append(f"{passed}/{len(outcome.reports)} passed · mean overall {mean:.0%}")
    usage = outcome.usage
    lines.append(
        f"Usage: {usage.calls} calls, {usage.tokens} tokens ({usage.cache_hits} cache hits)"
    )
    if outcome.stopped:
        lines.append(
            f"Stopped after {len(outcome.reports)}/{outcome.total} trajectories: {outcome.stopped}"
        )
    return lines
