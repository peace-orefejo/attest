from __future__ import annotations

from ..checks.profiles.signals import LIST_CHANGED_FILES, READ_DIFF

READ_FILE = "read_file"
GREP = "grep"
READ_GUIDELINES = "read_guidelines"

EVIDENCE_TOOLS: tuple[str, ...] = (READ_DIFF, LIST_CHANGED_FILES, READ_FILE, GREP, READ_GUIDELINES)

__all__ = [
    "EVIDENCE_TOOLS",
    "GREP",
    "LIST_CHANGED_FILES",
    "READ_DIFF",
    "READ_FILE",
    "READ_GUIDELINES",
]
