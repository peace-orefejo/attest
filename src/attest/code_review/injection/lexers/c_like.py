"""Lexer for languages with //, /* */ or # comments and quoted strings."""

from __future__ import annotations

from dataclasses import dataclass

from .base import Lexer, SegmentKind, SourceLines, Span, code_spans


@dataclass(frozen=True)
class Language:
    slash_comments: bool = True
    hash_comments: bool = False
    quotes: str = "\"'"
    multiline_quotes: str = ""
    triple_quotes: bool = False
    bare_kind: SegmentKind = "code"


C_STYLE = Language()
JS_STYLE = Language(quotes="\"'`", multiline_quotes="`")
GO_STYLE = Language(quotes="\"'`", multiline_quotes="`")
RUST_STYLE = Language(quotes="\"")
TRIPLE_STYLE = Language(triple_quotes=True)
PHP_STYLE = Language(hash_comments=True)
HASH_STYLE = Language(slash_comments=False, hash_comments=True)
PYTHON_STYLE = Language(slash_comments=False, hash_comments=True, triple_quotes=True)
YAML_STYLE = Language(slash_comments=False, hash_comments=True, bare_kind="string")


class _Scanner:
    def __init__(self, text: str, first_line: int, language: Language) -> None:
        self.text = text
        self.pos = 0
        self.line = first_line
        self.lang = language
        self.spans: list[Span] = []
        self.bare: dict[int, list[str]] = {}

    def run(self) -> list[Span]:
        while self.pos < len(self.text):
            self._step()
        bare = code_spans(self.bare, sep="")
        if self.lang.bare_kind != "code":
            bare = [Span(self.lang.bare_kind, span.line, span.text) for span in bare]
        return sorted(self.spans + bare, key=lambda span: span.line)

    def _step(self) -> None:
        text, pos, lang = self.text, self.pos, self.lang
        ch = text[pos]
        if lang.slash_comments and text.startswith("//", pos):
            self._until_eol("comment")
        elif lang.slash_comments and text.startswith("/*", pos):
            self._until("*/", "comment", pos + 2)
        elif lang.hash_comments and ch == "#" and (pos == 0 or text[pos - 1] in " \t\n"):
            self._until_eol("comment")
        elif lang.triple_quotes and text.startswith(('"""', "'''"), pos):
            self._until(text[pos:pos + 3], "string", pos + 3)
        elif ch in lang.quotes:
            self._quoted(ch)
        else:
            if ch == "\n":
                self.line += 1
            else:
                self.bare.setdefault(self.line, []).append(ch)
            self.pos += 1

    def _emit(self, kind: SegmentKind, start: int, end: int) -> None:
        body = self.text[start:end]
        if body.strip():
            self.spans.append(Span(kind, self.line, body))
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
        index = self.pos + 1
        while index < len(self.text):
            ch = self.text[index]
            if ch == "\\":
                index += 2
                continue
            if ch == quote:
                index += 1
                break
            if ch == "\n" and not multiline:
                break
            index += 1
        self._emit("string", self.pos, min(index, len(self.text)))


def lex_with(language: Language, lines: SourceLines) -> list[Span]:
    """Split contiguous source lines into comment, string and code spans."""
    if not lines:
        return []
    text = "\n".join(source for _, source in lines)
    return _Scanner(text, lines[0][0], language).run()


def lexer(language: Language) -> Lexer:
    """Return a lexer bound to one language configuration."""
    return lambda lines: lex_with(language, lines)
