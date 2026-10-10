"""Shared span type and lexer signature for the light code lexers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

SegmentKind = Literal["comment", "docstring", "string", "prose", "code"]
SourceLines = list[tuple[int, str]]


@dataclass(frozen=True)
class Span:
    kind: SegmentKind
    line: int
    text: str


Lexer = Callable[[SourceLines], list[Span]]


def code_spans(code_by_line: dict[int, list[str]], sep: str = " ") -> list[Span]:
    """One code span per line from the code fragments collected on it."""
    spans: list[Span] = []
    for line, parts in sorted(code_by_line.items()):
        text = sep.join(parts).strip()
        if text:
            spans.append(Span("code", line, text))
    return spans
