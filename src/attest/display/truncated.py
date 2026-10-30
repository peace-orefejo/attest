from __future__ import annotations

import re

from rich.console import Console, ConsoleOptions, RenderResult
from rich.measure import Measurement
from rich.text import Text

from .sanitize import terminal_safe
from .theme import one_line


class Truncated:
    """One line of text cut to the width it is given, ending in an ellipsis when cut."""

    def __init__(self, text: str) -> None:
        self.text = terminal_safe(re.sub(r"\s+", " ", text).strip())

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield Text(one_line(self.text, max(options.max_width, 1)), no_wrap=True)

    def __rich_measure__(self, console: Console, options: ConsoleOptions) -> Measurement:
        return Measurement(1, min(len(self.text), options.max_width))
