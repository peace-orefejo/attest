"""The lines above a code review's decisions: guidelines used, warnings and the injection scan."""

from __future__ import annotations

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

from ..code_review import ReviewResult
from .findings import findings_table
from .theme import STYLES, safe

_INJECTION_STYLES = {
    "clean": "pass",
    "suspicious": "warn",
    "payload": "fail",
    "compromised": "fail",
}


def context_section(result: ReviewResult) -> list[RenderableType]:
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(ratio=1)
    guidelines = _guidelines_row(result)
    if guidelines:
        table.add_row(*guidelines)
    for warning in result.warnings:
        table.add_row(
            Text("warning", style=STYLES["head"]),
            Text("!", style=STYLES["warn"]),
            safe(warning, STYLES["warn"]),
        )
    table.add_row(*_injection_row(result))
    parts: list[RenderableType] = [table]
    if result.injection.findings:
        parts.append(findings_table(result.injection.findings, indent=2))
    return parts


def _guidelines_row(result: ReviewResult) -> list[Text]:
    rules = result.guidelines
    if rules is None or (rules.builtin and not result.written):
        return []
    label = f"{rules.name} (built-in)" if rules.builtin else rules.name
    use = "guided attest's review" if rules.builtin else "checked"
    return [
        Text("guidelines", style=STYLES["head"]),
        safe(label, STYLES["label"]),
        Text(f"{len(rules.rules)} rules · {use}", style=STYLES["muted"]),
    ]


def _injection_row(result: ReviewResult) -> list[Text]:
    verdict = str(result.injection.metadata.get("verdict", "clean"))
    style = STYLES[_INJECTION_STYLES.get(verdict, "warn")]
    return [
        Text("injection", style=STYLES["head"]),
        safe(verdict, style),
        safe(result.injection.summary, STYLES["muted"]),
    ]
