"""Pattern and detector interfaces for injection scanning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ...content import Detection, TextSegment


@dataclass(frozen=True)
class RegexPattern:
    name: str
    pattern: str
    category: str = "instruction_override"
    confidence: float = 1.0
    severity: Literal["low", "medium", "high"] = "medium"


class InjectionDetector(Protocol):
    name: str

    def scan(self, segment: TextSegment) -> list[Detection]: ...
