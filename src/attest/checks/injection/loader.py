"""Loading of custom regex pattern packs from JSON."""

from __future__ import annotations

import json
from pathlib import Path

from .models import RegexPattern
from .regex_detector import RegexDetector


def load_regex_detector(path: Path) -> RegexDetector:
    """Load a named pattern pack from JSON for CLI and automation use."""
    try:
        payload = json.loads(path.read_text())
        raw_patterns = payload["patterns"]
        patterns = [RegexPattern(**item) for item in raw_patterns]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"Invalid regex pattern file {path}: {exc}") from exc
    return RegexDetector(patterns)
