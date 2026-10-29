"""Styles, badges and small text helpers shared by every renderer."""

from __future__ import annotations

import re

from rich.console import Console, ConsoleOptions, RenderResult
from rich.measure import Measurement
from rich.text import Text

from ..core import Finding, Severity

STYLES = {
    "pass": "bold green",
    "fail": "bold red",
    "warn": "bold yellow",
    "keep": "bold green",
    "drop": "bold red",
    "muted": "dim",
    "label": "bold",
    "head": "bold dim",
}

_MARKS = {Severity.PASS: ("✓", "green"), Severity.WARN: ("!", "yellow"), Severity.FAIL: ("✗", "red")}
_VERDICT_STYLES = {Severity.PASS: "green", Severity.WARN: "yellow", Severity.FAIL: "red"}
EVIDENCE_CHARS = 160


def badge(passed: bool) -> Text:
    return Text("PASS", style=STYLES["pass"]) if passed else Text("FAIL", style=STYLES["fail"])


def decision_badge(keep: bool) -> Text:
    return Text("KEEP", style=STYLES["keep"]) if keep else Text("DROP", style=STYLES["drop"])


def percent(score: float | None) -> str:
    return "—" if score is None else f"{score:.0%}"


def mark(severity: Severity) -> Text:
    symbol, style = _MARKS[severity]
    return Text(symbol, style=f"bold {style}")


def verdict(finding: Finding, severity: Severity) -> Text:
    return Text(finding.verdict, style=_VERDICT_STYLES[severity])


def one_line(text: str, limit: int = EVIDENCE_CHARS) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def location(finding: Finding) -> str:
    file = finding.metadata.get("file")
    line = finding.metadata.get("line")
    if file:
        where = f"{file}:{line}" if line is not None else str(file)
    else:
        where = f"step {finding.step}" if finding.step is not None else ""
    if where and finding.subject.startswith(where):
        where = ""
    affected = finding.metadata.get("affected_outputs")
    if isinstance(affected, list) and affected:
        where = f"{where}  affects #{', #'.join(str(i) for i in affected)}".strip()
    return where


class Truncated:
    """One line of text cut to the width it is given, ending in an ellipsis when cut."""

    def __init__(self, text: str) -> None:
        self.text = re.sub(r"\s+", " ", text).strip()

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield Text(one_line(self.text, max(options.max_width, 1)), no_wrap=True)

    def __rich_measure__(self, console: Console, options: ConsoleOptions) -> Measurement:
        return Measurement(1, min(len(self.text), options.max_width))
