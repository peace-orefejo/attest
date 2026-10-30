from __future__ import annotations

import re
from collections.abc import Iterator
from typing import cast

READ_DIFF = "read_diff"
LIST_CHANGED_FILES = "list_changed_files"
CODE_TOOLS: tuple[str, ...] = (READ_DIFF, LIST_CHANGED_FILES)

SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {
        "py",
        "pyi",
        "js",
        "jsx",
        "mjs",
        "cjs",
        "ts",
        "tsx",
        "go",
        "rs",
        "java",
        "kt",
        "kts",
        "scala",
        "c",
        "h",
        "cc",
        "cpp",
        "cxx",
        "hpp",
        "hh",
        "cs",
        "m",
        "mm",
        "swift",
        "rb",
        "php",
        "pl",
        "lua",
        "dart",
        "ex",
        "exs",
        "erl",
        "hs",
        "clj",
        "sh",
        "bash",
        "zsh",
        "ps1",
        "sql",
        "vue",
        "svelte",
        "r",
        "jl",
        "zig",
        "groovy",
        "gradle",
        "tf",
    }
)

MAX_SCAN_LINES = 400
MAX_LINE_CHARS = 2000
MAX_SCAN_CHARS = 200_000

_TOKEN_SPLIT = re.compile(r"[\s\"'`,;()\[\]{}<>=]+")
_STEM = re.compile(r"[\w.\-]+")
_TRAILING_LOCATION = re.compile(r"(?:#.*|(?::\d+)+)$")
_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@", re.MULTILINE)
_GIT_HEADER = re.compile(r"^diff --git ", re.MULTILINE)
_FILE_HEADERS = re.compile(r"^--- \S.*\n\+\+\+ \S", re.MULTILINE)
_CODE_LINE = re.compile(
    r"^(?:[\w./\\-]+:\d+:|\s*\d+[\t:|])?\s*(?:"
    r"(?:async\s+)?def\s+\w+\s*\(|class\s+\w+\s*[(:{<]|class\s+\w+\s+(?:extends|implements)\s"
    r"|from\s+[\w.]+\s+import\s+[\w*(]|import\s+[\w.]+(?:\s+as\s+\w+)?(?:\s*,\s*[\w.]+)*;?\s*$"
    r"|import\s+(?:\{|\*|\w+\s+from\s)|(?:export\s+)?(?:async\s+)?function\s*\w*\s*\("
    r"|(?:export\s+)?(?:const|let|var)\s+\w+\s*(?::\s*[\w<>\[\]]+\s*)?="
    r"|#include\s*[<\"]|(?:pub\s+)?fn\s+\w+\s*[<(]|func\s+(?:\(\w+\s+\*?\w+\)\s*)?\w+\s*\("
    r"|(?:public|private|protected)\s+(?:static\s+)?[\w<>\[\]]+\s+\w+\s*\("
    r"|(?:if|for|while|switch)\s*\(.*\)\s*\{\s*$|\}\s*else\b.*\{\s*$"
    r")"
)


def has_diff(text: str) -> bool:
    head = text[:MAX_SCAN_CHARS]
    return bool(_HUNK_HEADER.search(head) or _GIT_HEADER.search(head) or _FILE_HEADERS.search(head))


def code_line_count(text: str) -> int:
    lines = text[:MAX_SCAN_CHARS].splitlines()[:MAX_SCAN_LINES]
    return sum(1 for line in lines if _CODE_LINE.match(line[:MAX_LINE_CHARS]))


def source_file_in(value: object) -> str | None:
    for text in _strings(value):
        for token in _TOKEN_SPLIT.split(text):
            if _is_source_file(token):
                return token
    return None


def _is_source_file(token: str) -> bool:
    if "://" in token:
        token = token.split("://", 1)[1].partition("/")[2]
    token = _TRAILING_LOCATION.sub("", token.rstrip(".:"))
    name = token.replace("\\", "/").rsplit("/", 1)[-1]
    stem, dot, ext = name.rpartition(".")
    return bool(dot and stem and _STEM.fullmatch(stem)) and ext.lower() in SOURCE_EXTENSIONS


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in cast("dict[object, object]", value).values():
            yield from _strings(item)
    elif isinstance(value, list | tuple):
        for item in cast("list[object] | tuple[object, ...]", value):
            yield from _strings(item)
