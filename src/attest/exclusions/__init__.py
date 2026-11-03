"""User exclusion rules: gitignore-style patterns for files attest leaves out of the evidence."""

from __future__ import annotations

from .artifacts import (
    ARTIFACTS_EXCLUDED,
    ExcludedRun,
    exclude_artifacts,
    is_excluded_artifact,
    record_excluded,
)
from .loading import ATTESTIGNORE, MAX_PATTERN_FILE_BYTES, load_exclusions, read_pattern_file
from .rules import (
    EXCLUDED_REASON,
    MAX_PATTERNS,
    ExclusionError,
    Exclusions,
    ExclusionsInput,
    as_exclusions,
    excluded_note,
)

__all__ = [
    "ARTIFACTS_EXCLUDED",
    "ATTESTIGNORE",
    "EXCLUDED_REASON",
    "MAX_PATTERNS",
    "MAX_PATTERN_FILE_BYTES",
    "ExcludedRun",
    "ExclusionError",
    "Exclusions",
    "ExclusionsInput",
    "as_exclusions",
    "exclude_artifacts",
    "excluded_note",
    "is_excluded_artifact",
    "load_exclusions",
    "read_pattern_file",
    "record_excluded",
]
