from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from .detectors import RegexDetector
from .patterns import RegexPattern


class _PatternSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    pattern: str
    category: str = "instruction_override"
    confidence: float = 1.0
    severity: str = "medium"


class _PatternFile(BaseModel):
    patterns: list[_PatternSpec]


def load_regex_detector(path: Path) -> RegexDetector:
    """Load a named pattern pack from JSON for CLI and automation use."""
    try:
        pattern_file = _PatternFile.model_validate_json(path.read_text())
    except (OSError, ValidationError) as exc:
        raise ValueError(f"Invalid regex pattern file {path}: {exc}") from exc
    return RegexDetector([_to_pattern(spec) for spec in pattern_file.patterns])


def _to_pattern(spec: _PatternSpec) -> RegexPattern:
    severity = spec.severity
    if severity not in ("low", "medium", "high"):
        raise ValueError(f"Regex pattern {spec.name!r} severity must be low, medium, or high.")
    return RegexPattern(spec.name, spec.pattern, spec.category, spec.confidence, severity)
