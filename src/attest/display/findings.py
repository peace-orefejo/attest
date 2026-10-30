"""A finding list laid out as aligned columns: mark, verdict, then what was found and why."""

from __future__ import annotations

from collections.abc import Sequence

from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from ..results import Finding, Severity
from .theme import STYLES, location, mark, one_line, safe, verdict


def findings_table(findings: Sequence[Finding], indent: int = 4, *, notes: bool = False) -> Padding:
    """Lay out findings in columns; `notes` shows them as warnings whatever their severity."""
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(ratio=1, overflow="fold")
    for finding in findings:
        severity = Severity.WARN if notes else finding.severity
        table.add_row(mark(severity), verdict(finding, severity), _body(finding, severity))
    return Padding(table, (0, 0, 0, indent))


def _body(finding: Finding, severity: Severity) -> Text:
    text = Text()
    where = location(finding)
    if where:
        text.append_text(safe(where, "cyan"))
        text.append("  ")
    subject = finding.subject or "(no subject)"
    if severity is Severity.PASS:
        text.append_text(safe(subject, STYLES["muted"]))
        return text
    text.append_text(safe(subject))
    if finding.reason:
        text.append("\n")
        text.append_text(safe(finding.reason, STYLES["muted"]))
    if finding.evidence:
        text.append("\n")
        text.append("evidence  ", style=STYLES["head"])
        text.append_text(safe(one_line(finding.evidence), "dim italic"))
    return text
