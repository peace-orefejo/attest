"""Render recorded attest CLI output, colours included, as a terminal-window SVG for the docs.

    FORCE_COLOR=1 COLUMNS=96 attest run examples/trajectory.json > out.txt
    python docs/scripts/render_terminal.py out.txt docs/assets/terminal/attest-run.svg \
        --command "attest run examples/trajectory.json"
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

from rich.console import Console
from rich.text import Text


def render(output: str, command: str, title: str, width: int) -> str:
    console = Console(record=True, width=width, file=io.StringIO(), force_terminal=True,
                      color_system="truecolor")
    console.print(Text("$ ", style="dim") + Text(command, style="bold"))
    console.print(Text.from_ansi(output.rstrip("\n")), soft_wrap=True)
    return console.export_svg(title=title)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("transcript", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--command", required=True)
    parser.add_argument("--title", default="attest")
    parser.add_argument("--width", type=int, default=96)
    args = parser.parse_args()
    svg = render(args.transcript.read_text(), args.command, args.title, args.width)
    args.output.write_text(svg)


if __name__ == "__main__":
    main()
