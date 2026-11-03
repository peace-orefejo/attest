"""The --exclude, --exclude-file and --no-attestignore options, shared by run and review."""

from __future__ import annotations

from pathlib import Path

import typer

from ..exclusions import ExclusionError, Exclusions, load_exclusions

EXCLUDE_OPTION = typer.Option(
    [],
    "--exclude",
    help="Leave out files matching this gitignore-style pattern. Repeatable; applied after "
    "pattern files, so a later '!PATTERN' re-includes.",
)
EXCLUDE_FILE_OPTION = typer.Option(
    [],
    "--exclude-file",
    help="Read exclusion patterns from this gitignore-style file. Repeatable.",
)
ATTESTIGNORE_OPTION = typer.Option(
    True,
    "--attestignore/--no-attestignore",
    help="Read .attestignore from the current directory when it exists.",
)


def cli_exclusions(patterns: list[str], files: list[Path], discover: bool) -> Exclusions:
    """Load the exclusions the options ask for; any problem is invalid input (exit 2)."""
    try:
        return load_exclusions(patterns, files=files, discover=discover)
    except ExclusionError as exc:
        raise typer.BadParameter(str(exc)) from exc
