from __future__ import annotations

import io
import re
from typing import TypeAlias

from rich.console import Console, Group

from ..results import CheckResult, Report
from .checks import check_view, report_view

Result: TypeAlias = Report | CheckResult

_TRAILING = re.compile(r"[ \t]+((?:\x1b\[[0-9;]*m)*)$", re.MULTILINE)


def view(result: object, *, title: str | None = None) -> Group:
    """Build the rich renderable for a result."""
    if isinstance(result, Report):
        return report_view(result, title)
    if isinstance(result, CheckResult):
        return check_view(result, title)
    raise TypeError(f"Cannot render {type(result).__name__}.")


def strip_trailing(text: str) -> str:
    """Drop the padding rich adds at line ends, keeping any colour codes."""
    return _TRAILING.sub(r"\1", text)


def render(result: Result, *, title: str | None = None, width: int = 100) -> str:
    """Return a plain-text view of a result, for logs, files and tests."""
    buffer = io.StringIO()
    console = Console(file=buffer, width=width, color_system=None, highlight=False, soft_wrap=False)
    console.print(view(result, title=title))
    return strip_trailing(buffer.getvalue())


def show(result: Result, *, title: str | None = None, console: Console | None = None) -> None:
    """Print a result to the terminal with colour."""
    out = console or Console(highlight=False)
    with out.capture() as captured:
        out.print(view(result, title=title))
    out.file.write(strip_trailing(captured.get()))
    out.file.flush()
