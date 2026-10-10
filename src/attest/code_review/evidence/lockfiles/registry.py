"""Filename to lockfile parser lookup, and the summary entry point."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePosixPath

from . import cargo, go, npm, pnpm, python, yarn
from .base import DEFAULT_MAX_ENTRIES, VersionChange, changed_line_total, format_summary

Parser = Callable[[str], list[VersionChange]]

PARSERS: dict[str, Parser] = {
    "package-lock.json": npm.parse,
    "npm-shrinkwrap.json": npm.parse,
    "yarn.lock": yarn.parse,
    "pnpm-lock.yaml": pnpm.parse,
    "uv.lock": python.parse,
    "poetry.lock": python.parse,
    "Cargo.lock": cargo.parse,
    "go.sum": go.parse,
}


def parser_for(path: str) -> Parser | None:
    """Return the parser for a known lockfile path, or None."""
    return PARSERS.get(PurePosixPath(path).name)


def summarize_lockfile(
    path: str, diff_text: str, *, max_entries: int = DEFAULT_MAX_ENTRIES
) -> str | None:
    """Summarize a known lockfile diff as version changes, or None if it cannot be parsed."""
    parser = parser_for(path)
    if parser is None:
        return None
    try:
        changes = parser(diff_text)
    except Exception:
        return None
    return format_summary(path, changed_line_total(diff_text), changes, max_entries=max_entries)
