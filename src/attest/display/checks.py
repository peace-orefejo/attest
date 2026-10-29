"""Readable layouts for a CheckResult and a Report."""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from ..core import CheckResult, Report
from .findings import findings_table
from .theme import STYLES, badge, percent


def header(status: Text, title: str, subtitle: str = "") -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column(ratio=1)
    body = Text(title, style=STYLES["label"])
    if subtitle:
        body.append("\n")
        body.append(subtitle, style=STYLES["muted"])
    table.add_row(status, body)
    return table


def summary_table(results: list[CheckResult]) -> Table:
    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, header_style=STYLES["head"])
    table.add_column("CHECK", no_wrap=True)
    table.add_column("SCORE", justify="right", no_wrap=True)
    table.add_column("RESULT", no_wrap=True)
    table.add_column("SUMMARY", ratio=1)
    for result in results:
        table.add_row(Text(result.check), percent(result.score), badge(result.passed), Text(result.summary))
    return table


def details(result: CheckResult) -> list[RenderableType]:
    if not result.findings:
        return []
    return [Text(""), Text(f"  {result.check}", style=STYLES["label"]), findings_table(result.findings)]


def check_view(result: CheckResult, title: str | None = None) -> Group:
    facts = [result.check]
    if result.score is not None:
        facts.append(f"score {percent(result.score)}")
    if result.summary:
        facts.append(result.summary)
    parts: list[RenderableType] = [header(badge(result.passed), title or result.check, " · ".join(facts))]
    if result.findings:
        parts += [Text(""), findings_table(result.findings, indent=2)]
    return Group(*parts)


def report_view(report: Report, title: str | None = None) -> Group:
    checks = len(report.results)
    subtitle = f"overall {percent(report.overall_score)} · {checks} check{'s' if checks != 1 else ''}"
    parts: list[RenderableType] = [
        header(badge(report.passed), title or "Report", subtitle),
        Text(""),
        summary_table(report.results),
    ]
    for result in report.results:
        parts += details(result)
    return Group(*parts)
