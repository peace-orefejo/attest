"""Readable layouts for a code review: one row per output, then why each dropped output was dropped."""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from ..code_review import GateDecision, OutputDecision, ReviewResult
from ..code_review.models import INJECTION_VERDICTS
from .checks import header
from .findings import findings_table
from .theme import STYLES, Truncated, decision_badge, percent

_INJECTION_STYLES = {"clean": "pass", "suspicious": "warn", "payload": "fail", "compromised": "fail"}


def _guidelines_row(result: ReviewResult) -> list[Text]:
    rules = result.guidelines
    if rules is None or (rules.builtin and not result.written):
        return []
    label = f"{rules.name} (built-in)" if rules.builtin else rules.name
    use = "guided attest's review" if rules.builtin else "checked"
    return [Text("guidelines", style=STYLES["head"]), Text(label, style=STYLES["label"]),
            Text(f"{len(rules.rules)} rules · {use}", style=STYLES["muted"])]


def _context_section(result: ReviewResult) -> list[RenderableType]:
    verdict = str(result.injection.metadata.get("verdict", "clean"))
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(ratio=1)
    guidelines = _guidelines_row(result)
    if guidelines:
        table.add_row(*guidelines)
    for warning in result.warnings:
        table.add_row(Text("warning", style=STYLES["head"]), Text("!", style=STYLES["warn"]),
                      Text(warning, style=STYLES["warn"]))
    table.add_row(Text("injection", style=STYLES["head"]),
                  Text(verdict, style=STYLES[_INJECTION_STYLES.get(verdict, "warn")]),
                  Text(result.injection.summary, style=STYLES["muted"]))
    parts: list[RenderableType] = [table]
    if result.injection.findings:
        parts.append(findings_table(result.injection.findings, indent=2))
    return parts


def _fixed(rows: list[list[str]], header: str) -> int:
    return max([len(header), *(len(row) for row in rows)])


def _decisions_table(result: ReviewResult) -> Table:
    cells = [[str(d.index), d.output_type, d.mode, percent(d.score)] for d in result.decisions]
    columns = list(zip(*cells)) or [(), (), (), ()]
    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, header_style=STYLES["head"])
    for (header, justify), values in zip(
        [("#", "right"), ("TYPE", "left"), ("GATE", "left"), ("SCORE", "right")], columns
    ):
        table.add_column(header, justify=justify, no_wrap=True, min_width=_fixed(list(values), header))
    table.add_column("DECISION", no_wrap=True, min_width=len("DECISION"))
    table.add_column("OUTPUT", ratio=1)
    for decision, row in zip(result.decisions, cells):
        table.add_row(*(Text(cell) for cell in row), decision_badge(decision.keep), Truncated(decision.text))
    return table


def _omissions(decision: OutputDecision) -> list[RenderableType]:
    if not decision.omissions:
        return []
    text = Text("left out  ", style=STYLES["head"])
    text.append(", ".join(f"{o.path} ({o.reason.replace('_', ' ')})" for o in decision.omissions),
                style=STYLES["muted"])
    return [Padding(text, (0, 0, 0, 4))]


def _notes(notes: list, indent: int) -> list[RenderableType]:
    if not notes:
        return []
    return [Padding(Text("notes", style=STYLES["head"]), (0, 0, 0, indent)),
            findings_table(notes, indent, notes=True)]


def _own_notes(decision: OutputDecision) -> list:
    return [note for note in decision.notes if note.verdict not in INJECTION_VERDICTS]


def _decision_details(decision: OutputDecision) -> list[RenderableType]:
    notes = _own_notes(decision)
    if not decision.reasons and not notes and not decision.omissions:
        return []
    title = Text(f"  #{decision.index} {decision.output_type}  ", style=STYLES["label"])
    title.append_text(decision_badge(decision.keep))
    if decision.summary:
        title.append(f"  {decision.summary}", style=STYLES["muted"])
    parts: list[RenderableType] = [Text(""), title]
    if decision.reasons:
        parts.append(findings_table(decision.reasons))
    return parts + _notes(notes, 4) + _omissions(decision)


def review_view(result: ReviewResult, title: str | None = None) -> Group:
    total, kept = len(result.decisions), len(result.kept)
    subtitle = f"{kept} kept · {total - kept} dropped · {total} output{'s' if total != 1 else ''}"
    if result.written:
        subtitle += " · written by attest"
    status = decision_badge(True) if kept == total else Text(f"DROP {total - kept}", style=STYLES["drop"])
    parts: list[RenderableType] = [
        header(status, title or "Code review", subtitle),
        Text(""),
        *_context_section(result),
        Text(""),
        _decisions_table(result),
    ]
    for decision in result.decisions:
        parts += _decision_details(decision)
    return Group(*parts)


def gate_view(decision: GateDecision, title: str | None = None) -> Group:
    parts: list[RenderableType] = [header(decision_badge(decision.keep), title or "Gate decision",
                                          f"{decision.mode} gate")]
    if decision.reasons:
        parts += [Text(""), findings_table(decision.reasons, indent=2)]
    if decision.notes:
        parts += [Text(""), *_notes(decision.notes, 2)]
    return Group(*parts)
