"""Treat Markdown, reStructuredText and plain text as whole prose segments."""

from __future__ import annotations

from .base import SourceLines, Span


def lex(lines: SourceLines) -> list[Span]:
    """Return the lines as one prose span starting at the first line."""
    if not lines:
        return []
    return [Span("prose", lines[0][0], "\n".join(text for _, text in lines))]
