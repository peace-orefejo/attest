"""Deterministic detector that resolves answer_kind="auto" from a run's tool evidence."""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..trajectory import ToolCall, Trajectory
from .tool_names import LIST_CHANGED_FILES, READ_DIFF

CODE_TOOLS: tuple[str, ...] = (READ_DIFF, LIST_CHANGED_FILES)

SOURCE_EXTENSIONS: frozenset[str] = frozenset({
    "py", "pyi", "js", "jsx", "mjs", "cjs", "ts", "tsx", "go", "rs", "java", "kt", "kts",
    "scala", "c", "h", "cc", "cpp", "cxx", "hpp", "hh", "cs", "m", "mm", "swift", "rb",
    "php", "pl", "lua", "dart", "ex", "exs", "erl", "hs", "clj", "sh", "bash", "zsh",
    "ps1", "sql", "vue", "svelte", "r", "jl", "zig", "groovy", "gradle", "tf",
})

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
_MIN_CODE_LINES = 3
_MAX_SCAN_LINES = 400


def detect_answer_kind(traj: Trajectory) -> tuple[str, str]:
    """Return ("code" or "factual", reason) from the run's tool calls; no model calls."""
    calls = traj.tool_calls()
    if not calls:
        return "factual", "no tool calls recorded"
    for check in (_code_tool, _diff_output, _source_path, _code_shaped_output):
        for step, tc in calls:
            reason = check(tc)
            if reason:
                return "code", f"{reason} (step {step}, tool {tc.name})"
    return "factual", f"no code evidence in {len(calls)} tool call(s)"


def _code_tool(tc: ToolCall) -> str | None:
    return f"code review tool {tc.name} was called" if tc.name in CODE_TOOLS else None


def _diff_output(tc: ToolCall) -> str | None:
    text = tc.output
    if _HUNK_HEADER.search(text) or _GIT_HEADER.search(text) or _FILE_HEADERS.search(text):
        return "unified diff in tool output"
    return None


def _source_path(tc: ToolCall) -> str | None:
    for value in _strings(tc.arguments):
        for token in _TOKEN_SPLIT.split(value):
            if _is_source_file(token):
                return f"source file {token!r} in tool arguments"
    return None


def _is_source_file(token: str) -> bool:
    if "://" in token:
        token = token.split("://", 1)[1].partition("/")[2]
    token = _TRAILING_LOCATION.sub("", token.rstrip(".:"))
    name = token.replace("\\", "/").rsplit("/", 1)[-1]
    stem, dot, ext = name.rpartition(".")
    return bool(dot and stem and _STEM.fullmatch(stem)) and ext.lower() in SOURCE_EXTENSIONS


def _code_shaped_output(tc: ToolCall) -> str | None:
    lines = tc.output.splitlines()[:_MAX_SCAN_LINES]
    hits = sum(1 for line in lines if _CODE_LINE.match(line))
    if hits >= _MIN_CODE_LINES:
        return f"code-shaped tool output ({hits} code lines)"
    return None


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)
