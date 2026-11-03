"""User exclusion rules: gitignore-style patterns for files attest leaves out of the evidence."""

from __future__ import annotations

from .artifacts import (
    ARTIFACTS_EXCLUDED,
    ExcludedRun,
    exclude_artifacts,
    is_excluded_artifact,
    record_excluded,
)
from .changed_sources import changed_sources
from .loading import (
    ATTESTIGNORE,
    MAX_PATTERN_FILE_BYTES,
    ExclusionsInput,
    as_exclusions,
    load_exclusions,
    read_pattern_file,
)
from .resolved import cwd_roots, path_forms, within_cwd
from .rules import (
    EXCLUDED_REASON,
    MAX_PATH_CHARS,
    MAX_PATH_DEPTH,
    MAX_PATTERNS,
    ExclusionError,
    Exclusions,
    excluded_note,
)

__all__ = [
    "ARTIFACTS_EXCLUDED",
    "ATTESTIGNORE",
    "EXCLUDED_REASON",
    "MAX_PATH_CHARS",
    "MAX_PATH_DEPTH",
    "MAX_PATTERNS",
    "MAX_PATTERN_FILE_BYTES",
    "ExcludedRun",
    "ExclusionError",
    "Exclusions",
    "ExclusionsInput",
    "as_exclusions",
    "changed_sources",
    "cwd_roots",
    "exclude_artifacts",
    "excluded_note",
    "is_excluded_artifact",
    "load_exclusions",
    "path_forms",
    "read_pattern_file",
    "record_excluded",
    "within_cwd",
]
