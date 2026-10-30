"""Treat Markdown, reStructuredText and plain text as whole prose segments."""

from __future__ import annotations

from .base import SourceLines, Span


def lex(lines: SourceLines) -> list[Span]:
    """Return the lines as one prose span starting at the first line."""
    if not lines:
        return []
    return [Span(kind="prose", line=lines[0][0], text="\n".join(text for _, text in lines))]
