"""Lexer for languages with //, /* */ or # comments and quoted strings."""

from __future__ import annotations

import re
from functools import cache

from .base import Lexer, SegmentKind, SourceLines, Span, code_spans
from .languages import (
    C_STYLE,
    GO_STYLE,
    HASH_STYLE,
    JS_STYLE,
    PHP_STYLE,
    PYTHON_STYLE,
    RUBY_STYLE,
    RUST_STYLE,
    TRIPLE_STYLE,
    YAML_STYLE,
    Language,
)

__all__ = [
    "C_STYLE",
    "GO_STYLE",
    "HASH_STYLE",
    "JS_STYLE",
    "PHP_STYLE",
    "PYTHON_STYLE",
    "RUBY_STYLE",
    "RUST_STYLE",
    "TRIPLE_STYLE",
    "YAML_STYLE",
    "Language",
    "lex_with",
    "lexer",
]


def lex_with(language: Language, lines: SourceLines) -> list[Span]:
    """Split contiguous source lines into comment, string and code spans."""
    if not lines:
        return []
    text = "\n".join(source for _, source in lines)
    return _Scanner(text, lines[0][0], language).run()


def lexer(language: Language) -> Lexer:
    """Return a lexer bound to one language configuration."""
    return lambda lines: lex_with(language, lines)


def _special_chars(language: Language) -> re.Pattern[str]:
    chars = "\n" + language.quotes
    if language.slash_comments:
        chars += "/"
    if language.hash_comments:
        chars += "#"
    return re.compile(f"[{re.escape(chars)}]")


@cache
def _string_stops(quote: str) -> re.Pattern[str]:
    return re.compile(f"[\\\\\n{re.escape(quote)}]")


class _Scanner:
    def __init__(self, text: str, first_line: int, language: Language) -> None:
        self.text = text
        self.pos = 0
        self.line = first_line
        self.lang = language
        self.special = _special_chars(language)
        self.spans: list[Span] = []
        self.bare: dict[int, list[str]] = {}

    def run(self) -> list[Span]:
        while self.pos < len(self.text):
            self._step()
        bare = code_spans(self.bare, sep="")
        if self.lang.bare_kind != "code":
            bare = [Span(kind=self.lang.bare_kind, line=s.line, text=s.text) for s in bare]
        return sorted(self.spans + bare, key=lambda span: span.line)

    def _step(self) -> None:
        text, pos, lang = self.text, self.pos, self.lang
        if lang.slash_comments and text.startswith("//", pos):
            self._until_eol("comment")
        elif lang.slash_comments and text.startswith("/*", pos):
            self._until("*/", "comment", pos + 2)
        elif lang.hash_comments and text[pos] == "#" and self._hash_starts_comment():
            self._until_eol("comment")
        elif lang.triple_quotes and text.startswith(('"""', "'''"), pos):
            self._until(text[pos : pos + 3], "string", pos + 3)
        elif text[pos] in lang.quotes:
            self._quoted(text[pos])
        else:
            self._bare()

    def _hash_starts_comment(self) -> bool:
        if self.lang.hash_anywhere or self.pos == 0:
            return True
        return self.text[self.pos - 1] in self.lang.hash_after

    def _bare(self) -> None:
        if self.text[self.pos] == "\n":
            self.line += 1
            self.pos += 1
            return
        found = self.special.search(self.text, self.pos + 1)
        end = found.start() if found else len(self.text)
        self.bare.setdefault(self.line, []).append(self.text[self.pos : end])
        self.pos = end

    def _emit(self, kind: SegmentKind, start: int, end: int) -> None:
        body = self.text[start:end]
        if body.strip():
            self.spans.append(Span(kind=kind, line=self.line, text=body))
        self.line += body.count("\n")
        self.pos = end

    def _until_eol(self, kind: SegmentKind) -> None:
        end = self.text.find("\n", self.pos)
        self._emit(kind, self.pos, len(self.text) if end < 0 else end)

    def _until(self, closer: str, kind: SegmentKind, search_from: int) -> None:
        end = self.text.find(closer, search_from)
        self._emit(kind, self.pos, len(self.text) if end < 0 else end + len(closer))

    def _quoted(self, quote: str) -> None:
        multiline = quote in self.lang.multiline_quotes
        stops = _string_stops(quote)
        index = self.pos + 1
        while True:
            found = stops.search(self.text, index)
            if found is None:
                index = len(self.text)
                break
            index = found.start()
            if found.group() == "\\":
                index += 2
            elif found.group() == quote:
                index += 1
                break
            elif multiline:
                index += 1
            else:
                break
        self._emit("string", self.pos, min(index, len(self.text)))
