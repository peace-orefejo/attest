"""Python lexer built on the standard tokenizer, with a c_like fallback for partial code."""

from __future__ import annotations

import io
import textwrap
import tokenize

from .base import SourceLines, Span, code_spans
from .c_like import PYTHON_STYLE, lex_with

_STATEMENT_START = {tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT}
_SKIPPED = {tokenize.NL, tokenize.COMMENT, tokenize.ENCODING}
_CODE_SKIP = {
    tokenize.NEWLINE,
    tokenize.NL,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENDMARKER,
    tokenize.ENCODING,
}
_STRING_STARTS = {getattr(tokenize, name, -1) for name in ("FSTRING_START", "TSTRING_START")} - {-1}
_STRING_MIDDLES = {getattr(tokenize, name, -1) for name in ("FSTRING_MIDDLE", "TSTRING_MIDDLE")} - {
    -1
}
_STRING_ENDS = {getattr(tokenize, name, -1) for name in ("FSTRING_END", "TSTRING_END")} - {-1}


def lex(lines: SourceLines) -> list[Span]:
    """Split contiguous Python lines into comment, docstring, string and code spans."""
    if not lines:
        return []
    try:
        tokens = _tokens(lines)
    except (tokenize.TokenError, SyntaxError):
        return lex_with(PYTHON_STYLE, lines)
    return _spans(tokens, lines[0][0])


def _tokens(lines: SourceLines) -> list[tokenize.TokenInfo]:
    source = textwrap.dedent("\n".join(text for _, text in lines)) + "\n"
    return list(tokenize.generate_tokens(io.StringIO(source).readline))


def _neighbour(
    tokens: list[tokenize.TokenInfo], index: int, step: int
) -> tokenize.TokenInfo | None:
    position = index + step
    while 0 <= position < len(tokens):
        if tokens[position].type not in _SKIPPED:
            return tokens[position]
        position += step
    return None


def _is_docstring(tokens: list[tokenize.TokenInfo], index: int) -> bool:
    before = _neighbour(tokens, index, -1)
    after = _neighbour(tokens, index, 1)
    starts = before is None or before.type in _STATEMENT_START
    ends = after is None or after.type in {tokenize.NEWLINE, tokenize.ENDMARKER}
    return starts and ends


def _spans(tokens: list[tokenize.TokenInfo], first_line: int) -> list[Span]:
    spans: list[Span] = []
    code: dict[int, list[str]] = {}
    templates: list[tuple[int, list[str]]] = []
    for index, token in enumerate(tokens):
        line = first_line + token.start[0] - 1
        if token.type == tokenize.COMMENT:
            spans.append(Span(kind="comment", line=line, text=token.string))
        elif token.type == tokenize.STRING:
            kind = "docstring" if _is_docstring(tokens, index) else "string"
            spans.append(Span(kind=kind, line=line, text=token.string))
        elif token.type in _STRING_STARTS:
            templates.append((line, [token.string]))
        elif token.type in _STRING_MIDDLES and templates:
            templates[-1][1].append(token.string)
        elif token.type in _STRING_ENDS and templates:
            start, parts = templates.pop()
            spans.append(Span(kind="string", line=start, text="".join(parts) + token.string))
        elif templates:
            continue
        elif token.type not in _CODE_SKIP:
            code.setdefault(line, []).append(token.string)
    return sorted(spans + code_spans(code), key=lambda span: span.line)
