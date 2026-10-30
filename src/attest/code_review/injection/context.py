"""Context rules that lower confidence for quoted examples in tests and docs."""

from __future__ import annotations

import re

from .segments import Segment

GENERIC_FACTOR = 0.7
REFERENCE_FACTOR = 0.6
PROSE_BAIT_FACTOR = 0.6

_TEST_PATH = re.compile(
    r"(?:^|/)(?:tests?|__tests__|specs?|fixtures)/|(?:^|/)test_[^/]*$|_test\.\w+$|"
    r"\.(?:test|spec)\.\w+$|(?:^|/)conftest\.py$",
    re.IGNORECASE,
)
_DOC_PATH = re.compile(
    r"(?:^|/)docs?/|\.(?:md|markdown|rst|txt)$|(?:^|/)SECURITY[^/]*$", re.IGNORECASE
)
_QUOTES = (('"', '"'), ("`", "`"), ("“", "”"))


def is_test_path(path: str) -> bool:
    return bool(_TEST_PATH.search(path))


def is_doc_path(path: str) -> bool:
    return bool(_DOC_PATH.search(path))


def is_reference_path(path: str) -> bool:
    """True for test and documentation files, where quoting an attack is normal."""
    return is_test_path(path) or is_doc_path(path)


def quoted(text: str, start: int, end: int) -> bool:
    """True when the span sits between a quote pair on its own line."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    before = text[line_start:start]
    after = text[end:] if line_end < 0 else text[end:line_end]
    return any(opener in before and closer in after for opener, closer in _QUOTES)


def reference_example(segment: Segment, start: int, end: int) -> bool:
    """True for a test-file string literal, or quoted text in a test or doc file."""
    in_test = is_test_path(segment.file)
    if in_test and segment.kind == "string":
        return True
    return is_reference_path(segment.file) and quoted(segment.text, start, end)
