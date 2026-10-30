"""Styles, badges and small text helpers shared by every renderer."""

from __future__ import annotations

import re
from typing import cast

from rich.text import Text

from ..results import Finding, Severity
from .sanitize import terminal_safe

STYLES = {
    "pass": "bold green",
    "fail": "bold red",
    "warn": "bold yellow",
    "muted": "dim",
    "label": "bold",
    "head": "bold dim",
}

_MARKS = {
    Severity.PASS: ("✓", "green"),
    Severity.WARN: ("!", "yellow"),
    Severity.FAIL: ("✗", "red"),
}
_VERDICT_STYLES = {Severity.PASS: "green", Severity.WARN: "yellow", Severity.FAIL: "red"}
EVIDENCE_CHARS = 160


def safe(text: str, style: str = "") -> Text:
    return Text(terminal_safe(text), style=style)


def badge(passed: bool) -> Text:
    return Text("PASS", style=STYLES["pass"]) if passed else Text("FAIL", style=STYLES["fail"])


def percent(score: float | None) -> str:
    return "—" if score is None else f"{score:.0%}"


def mark(severity: Severity) -> Text:
    symbol, style = _MARKS[severity]
    return Text(symbol, style=f"bold {style}")


def verdict(finding: Finding, severity: Severity) -> Text:
    return safe(finding.verdict, _VERDICT_STYLES[severity])


def one_line(text: str, limit: int = EVIDENCE_CHARS) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def location(finding: Finding) -> str:
    where = _place(finding)
    if where and finding.subject.startswith(where):
        where = ""
    affected = finding.metadata.get("affected_outputs")
    if isinstance(affected, list) and affected:
        numbers = ", #".join(str(i) for i in cast(list[object], affected))
        where = f"{where}  affects #{numbers}".strip()
    return where


def _place(finding: Finding) -> str:
    file = finding.metadata.get("file")
    line = finding.metadata.get("line")
    if file:
        return f"{file}:{line}" if line is not None else str(file)
    return f"step {finding.step}" if finding.step is not None else ""
