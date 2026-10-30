"""Readable layouts for a CheckResult and a Report."""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from ..results import CheckResult, Report
from .findings import findings_table
from .theme import STYLES, badge, percent, safe


def header(status: Text, title: str, subtitle: str = "") -> Table:
    """A status badge beside a bold title, with an optional muted subtitle under it."""
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column(ratio=1)
    body = safe(title, STYLES["label"])
    if subtitle:
        body.append("\n")
        body.append_text(safe(subtitle, STYLES["muted"]))
    table.add_row(status, body)
    return table


def check_view(result: CheckResult, title: str | None = None) -> Group:
    facts = [result.check]
    if result.score is not None:
        facts.append(f"score {percent(result.score)}")
    if result.summary:
        facts.append(result.summary)
    parts: list[RenderableType] = [
        header(badge(result.passed), title or result.check, " · ".join(facts))
    ]
    if result.findings:
        parts += [Text(""), findings_table(result.findings, indent=2)]
    return Group(*parts)


def report_view(report: Report, title: str | None = None) -> Group:
    checks = len(report.results)
    plural = "s" if checks != 1 else ""
    subtitle = f"overall {percent(report.overall_score)} · {checks} check{plural}"
    parts: list[RenderableType] = [
        header(badge(report.passed), title or "Report", subtitle),
        Text(""),
        _summary_table(report.results),
    ]
    for result in report.results:
        parts += _details(result)
    return Group(*parts)


def _summary_table(results: list[CheckResult]) -> Table:
    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, header_style=STYLES["head"])
    table.add_column("CHECK", no_wrap=True)
    table.add_column("SCORE", justify="right", no_wrap=True)
    table.add_column("RESULT", no_wrap=True)
    table.add_column("SUMMARY", ratio=1)
    for result in results:
        table.add_row(
            safe(result.check), percent(result.score), badge(result.passed), safe(result.summary)
        )
    return table


def _details(result: CheckResult) -> list[RenderableType]:
    if not result.findings:
        return []
    return [
        Text(""),
        safe(f"  {result.check}", STYLES["label"]),
        findings_table(result.findings),
    ]
