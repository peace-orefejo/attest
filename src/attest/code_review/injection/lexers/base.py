"""Shared span type and lexer signature for the light code lexers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict

SegmentKind = Literal["comment", "docstring", "string", "prose", "code"]
SourceLines: TypeAlias = list[tuple[int, str]]


class Span(BaseModel):
    """A run of source text of one kind, starting on a given new-side line."""

    model_config = ConfigDict(frozen=True)

    kind: SegmentKind
    line: int
    text: str


Lexer: TypeAlias = Callable[[SourceLines], list[Span]]


def code_spans(code_by_line: dict[int, list[str]], sep: str = " ") -> list[Span]:
    """One code span per line from the code fragments collected on it."""
    spans: list[Span] = []
    for line, parts in sorted(code_by_line.items()):
        text = sep.join(parts).strip()
        if text:
            spans.append(Span(kind="code", line=line, text=text))
    return spans
