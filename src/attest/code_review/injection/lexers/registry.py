"""Pick a lexer from a file path's extension."""

from __future__ import annotations

from pathlib import PurePosixPath

from . import prose, python
from .base import Lexer
from .c_like import (C_STYLE, GO_STYLE, HASH_STYLE, JS_STYLE, PHP_STYLE, RUST_STYLE,
                     TRIPLE_STYLE, YAML_STYLE, lexer)

_BY_SUFFIX: dict[str, Lexer] = {
    **dict.fromkeys((".py", ".pyi"), python.lex),
    **dict.fromkeys((".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"), lexer(JS_STYLE)),
    **dict.fromkeys((".java", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".cs"), lexer(C_STYLE)),
    ".go": lexer(GO_STYLE),
    ".rs": lexer(RUST_STYLE),
    **dict.fromkeys((".kt", ".kts", ".swift"), lexer(TRIPLE_STYLE)),
    ".php": lexer(PHP_STYLE),
    **dict.fromkeys((".rb", ".sh", ".bash", ".zsh"), lexer(HASH_STYLE)),
    **dict.fromkeys((".yml", ".yaml"), lexer(YAML_STYLE)),
    **dict.fromkeys((".md", ".markdown", ".txt", ".rst"), prose.lex),
}


def lexer_for(path: str) -> Lexer:
    """Return the lexer for a path, treating unknown file types as prose."""
    return _BY_SUFFIX.get(PurePosixPath(path).suffix.lower(), prose.lex)
