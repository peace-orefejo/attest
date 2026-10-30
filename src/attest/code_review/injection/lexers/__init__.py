"""Light lexers that split source lines into comment, docstring, string, prose and code."""

from .base import Lexer, SegmentKind, SourceLines, Span
from .registry import lexer_for

__all__ = ["Lexer", "SegmentKind", "SourceLines", "Span", "lexer_for"]
