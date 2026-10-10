"""The result of extracting one artifact."""

from __future__ import annotations

from dataclasses import dataclass

from ..core import TextSegment


@dataclass
class ExtractionOutcome:
    segments: list[TextSegment]
    warning: str | None = None
    truncated: bool = False
    inspected: bool = False
