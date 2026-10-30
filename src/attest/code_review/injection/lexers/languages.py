"""Comment and string syntax for each language family the c_like lexer handles."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .base import SegmentKind

SHELL_WORD_BREAKS = " \t\n;|&()"


class Language(BaseModel):
    """How one language family writes comments and string literals."""

    model_config = ConfigDict(frozen=True)

    slash_comments: bool = True
    hash_comments: bool = False
    hash_anywhere: bool = False
    hash_after: str = " \t\n"
    quotes: str = "\"'"
    multiline_quotes: str = ""
    triple_quotes: bool = False
    bare_kind: SegmentKind = "code"


C_STYLE = Language()
JS_STYLE = Language(quotes="\"'`", multiline_quotes="`")
GO_STYLE = Language(quotes="\"'`", multiline_quotes="`")
RUST_STYLE = Language(quotes='"', multiline_quotes='"')
TRIPLE_STYLE = Language(triple_quotes=True)
PHP_STYLE = Language(hash_comments=True, hash_anywhere=True)
HASH_STYLE = Language(slash_comments=False, hash_comments=True, hash_after=SHELL_WORD_BREAKS)
RUBY_STYLE = Language(slash_comments=False, hash_comments=True, hash_anywhere=True)
PYTHON_STYLE = Language(
    slash_comments=False, hash_comments=True, hash_anywhere=True, triple_quotes=True
)
YAML_STYLE = Language(slash_comments=False, hash_comments=True, bare_kind="string")
