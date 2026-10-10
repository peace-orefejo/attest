"""Python lexer built on the standard tokenizer, with a c_like fallback for partial code."""

from __future__ import annotations

import io
import textwrap
import tokenize

from .base import SourceLines, Span, code_spans
from .c_like import PYTHON_STYLE, lex_with

_STATEMENT_START = {tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT}
_SKIPPED = {tokenize.NL, tokenize.COMMENT, tokenize.ENCODING}
_CODE_SKIP = {tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.DEDENT,
              tokenize.ENDMARKER, tokenize.ENCODING}
_FSTRING_START = getattr(tokenize, "FSTRING_START", -1)
_FSTRING_MIDDLE = getattr(tokenize, "FSTRING_MIDDLE", -1)
_FSTRING_END = getattr(tokenize, "FSTRING_END", -1)


def _tokens(lines: SourceLines) -> list[tokenize.TokenInfo]:
    source = textwrap.dedent("\n".join(text for _, text in lines)) + "\n"
    return list(tokenize.generate_tokens(io.StringIO(source).readline))


def _is_docstring(tokens: list[tokenize.TokenInfo], index: int) -> bool:
    before = next((t for t in reversed(tokens[:index]) if t.type not in _SKIPPED), None)
    after = next((t for t in tokens[index + 1:] if t.type not in _SKIPPED), None)
    starts = before is None or before.type in _STATEMENT_START
    ends = after is None or after.type in {tokenize.NEWLINE, tokenize.ENDMARKER}
    return starts and ends


def _spans(tokens: list[tokenize.TokenInfo], first_line: int) -> list[Span]:
    spans: list[Span] = []
    code: dict[int, list[str]] = {}
    fstrings: list[tuple[int, list[str]]] = []
    for index, token in enumerate(tokens):
        line = first_line + token.start[0] - 1
        if token.type == tokenize.COMMENT:
            spans.append(Span("comment", line, token.string))
        elif token.type == tokenize.STRING:
            kind = "docstring" if _is_docstring(tokens, index) else "string"
            spans.append(Span(kind, line, token.string))
        elif token.type == _FSTRING_START:
            fstrings.append((line, [token.string]))
        elif token.type == _FSTRING_MIDDLE and fstrings:
            fstrings[-1][1].append(token.string)
        elif token.type == _FSTRING_END and fstrings:
            start, parts = fstrings.pop()
            spans.append(Span("string", start, "".join(parts) + token.string))
        elif fstrings:
            continue
        elif token.type not in _CODE_SKIP:
            code.setdefault(line, []).append(token.string)
    return sorted(spans + code_spans(code), key=lambda span: span.line)


def lex(lines: SourceLines) -> list[Span]:
    """Split contiguous Python lines into comment, docstring, string and code spans."""
    if not lines:
        return []
    try:
        tokens = _tokens(lines)
    except (tokenize.TokenError, SyntaxError):
        return lex_with(PYTHON_STYLE, lines)
    return _spans(tokens, lines[0][0])
