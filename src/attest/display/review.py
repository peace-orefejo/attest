"""Readable layouts for a code review: a row per output, then why each dropped output dropped."""

from __future__ import annotations

from collections.abc import Sequence

from rich import box
from rich.console import Group, JustifyMethod, RenderableType
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from ..code_review import GateDecision, OutputDecision, ReviewResult
from ..code_review.models import INJECTION_VERDICTS
from ..results import Finding
from .checks import header
from .findings import findings_table
from .review_context import context_section
from .theme import STYLES, decision_badge, percent, safe
from .truncated import Truncated

_FIXED_COLUMNS: tuple[tuple[str, JustifyMethod], ...] = (
    ("#", "right"),
    ("TYPE", "left"),
    ("GATE", "left"),
    ("SCORE", "right"),
)


def review_view(result: ReviewResult, title: str | None = None) -> Group:
    total, kept = len(result.decisions), len(result.kept)
    plural = "s" if total != 1 else ""
    subtitle = f"{kept} kept · {total - kept} dropped · {total} output{plural}"
    if result.written:
        subtitle += " · written by attest"
    status = (
        decision_badge(True)
        if kept == total
        else Text(f"DROP {total - kept}", style=STYLES["drop"])
    )
    parts: list[RenderableType] = [
        header(status, title or "Code review", subtitle),
        Text(""),
        *context_section(result),
        Text(""),
        _decisions_table(result),
    ]
    for decision in result.decisions:
        parts += _decision_details(decision)
    return Group(*parts)


def gate_view(decision: GateDecision, title: str | None = None) -> Group:
    parts: list[RenderableType] = [
        header(decision_badge(decision.keep), title or "Gate decision", f"{decision.mode} gate")
    ]
    if decision.reasons:
        parts += [Text(""), findings_table(decision.reasons, indent=2)]
    if decision.notes:
        parts += [Text(""), *_notes(decision.notes, 2)]
    return Group(*parts)


def _decisions_table(result: ReviewResult) -> Table:
    rows = [[str(d.index), d.output_type, d.mode, percent(d.score)] for d in result.decisions]
    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, header_style=STYLES["head"])
    for column, (name, justify) in enumerate(_FIXED_COLUMNS):
        width = max([len(name), *(len(row[column]) for row in rows)])
        table.add_column(name, justify=justify, no_wrap=True, min_width=width)
    table.add_column("DECISION", no_wrap=True, min_width=len("DECISION"))
    table.add_column("OUTPUT", ratio=1)
    for decision, row in zip(result.decisions, rows, strict=True):
        cells = [Text(cell) for cell in row]
        table.add_row(*cells, decision_badge(decision.keep), Truncated(decision.text))
    return table


def _decision_details(decision: OutputDecision) -> list[RenderableType]:
    notes = _own_notes(decision)
    if not decision.reasons and not notes and not decision.omissions:
        return []
    title = Text(f"  #{decision.index} {decision.output_type}  ", style=STYLES["label"])
    title.append_text(decision_badge(decision.keep))
    if decision.summary:
        title.append_text(safe(f"  {decision.summary}", STYLES["muted"]))
    parts: list[RenderableType] = [Text(""), title]
    if decision.reasons:
        parts.append(findings_table(decision.reasons))
    return parts + _notes(notes, 4) + _omissions(decision)


def _own_notes(decision: OutputDecision) -> list[Finding]:
    injection: tuple[str, ...] = INJECTION_VERDICTS
    return [note for note in decision.notes if note.verdict not in injection]


def _notes(notes: Sequence[Finding], indent: int) -> list[RenderableType]:
    if not notes:
        return []
    return [
        Padding(Text("notes", style=STYLES["head"]), (0, 0, 0, indent)),
        findings_table(notes, indent, notes=True),
    ]


def _omissions(decision: OutputDecision) -> list[RenderableType]:
    if not decision.omissions:
        return []
    listed = ", ".join(f"{o.path} ({o.reason.replace('_', ' ')})" for o in decision.omissions)
    text = Text("left out  ", style=STYLES["head"])
    text.append_text(safe(listed, STYLES["muted"]))
    return [Padding(text, (0, 0, 0, 4))]
