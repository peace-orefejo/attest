"""The --exclude, --exclude-file and --no-attestignore options, shared by run and review."""

from __future__ import annotations

from pathlib import Path

import typer

from ..code_review.models import PullRequest
from ..exclusions import ExclusionError, Exclusions, changed_sources, load_exclusions

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

ALLOW_PR_EXCLUSIONS_OPTION = typer.Option(
    False,
    "--allow-pr-attestignore",
    help="Use exclusion files even when the reviewed pull request changes them. Without it, "
    "attest refuses, since the pull request could hide its own changes.",
)


def cli_exclusions(patterns: list[str], files: list[Path], discover: bool) -> Exclusions:
    """Load the exclusions the options ask for; any problem is invalid input (exit 2)."""
    try:
        return load_exclusions(patterns, files=files, discover=discover)
    except ExclusionError as exc:
        raise typer.BadParameter(str(exc)) from exc


def refuse_pr_edited_exclusions(exclusions: Exclusions, pr: PullRequest, *, allowed: bool) -> None:
    """Refuse (exit 2) when the pull request changes a file the patterns were read from."""
    edited = changed_sources(exclusions.sources, [*pr.diffs, *pr.changed_files])
    if not edited or allowed:
        return
    names = ", ".join(edited)
    raise typer.BadParameter(
        f"The pull request changes {names}, which exclusion patterns were read from, so it "
        "could hide its own changes from review. Read the patterns from the base branch "
        "instead (for example `git show origin/main:.attestignore > base.attestignore`, then "
        "--no-attestignore --exclude-file base.attestignore), or pass --allow-pr-attestignore "
        "to use the pull request's patterns anyway."
    )
