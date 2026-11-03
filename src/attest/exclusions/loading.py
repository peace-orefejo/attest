"""Read exclusion patterns from `.attestignore`-style files and combine them with direct ones."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from .rules import ExclusionError, Exclusions

ATTESTIGNORE = ".attestignore"
MAX_PATTERN_FILE_BYTES = 1_048_576

PathInput = str | os.PathLike[str]


def load_exclusions(
    patterns: Sequence[str] = (),
    *,
    files: Sequence[PathInput] = (),
    discover: bool = False,
    root: PathInput | None = None,
) -> Exclusions:
    """Build exclusions from pattern files, then `patterns`, in that order.

    With `discover=True`, `.attestignore` in `root` (the current directory by default) is read
    first when it exists. Then each of `files`, then `patterns`, so a later `!` pattern can
    re-include what an earlier one excluded. A file that can't be read, isn't UTF-8 or is over
    1 MB raises `ExclusionError`; it is never silently skipped.
    """
    sources = [*_discovered(discover, root), *(Path(file) for file in files)]
    lines: list[str] = []
    for source in sources:
        lines.extend(read_pattern_file(source))
    return Exclusions(
        patterns=(*lines, *patterns), sources=tuple(str(source) for source in sources)
    )


def read_pattern_file(path: PathInput) -> list[str]:
    """Read one pattern file's lines, refusing files over `MAX_PATTERN_FILE_BYTES`."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_PATTERN_FILE_BYTES + 1)
    except OSError as exc:
        reason = exc.strerror or type(exc).__name__
        raise ExclusionError(f"Could not read exclusion file {path}: {reason}.") from exc
    if len(raw) > MAX_PATTERN_FILE_BYTES:
        raise ExclusionError(
            f"Exclusion file {path} is over the {MAX_PATTERN_FILE_BYTES:,}-byte (1 MB) limit."
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ExclusionError(f"Exclusion file {path} is not UTF-8 text.") from exc
    return text.splitlines()


def _discovered(discover: bool, root: PathInput | None) -> list[Path]:
    if not discover:
        return []
    candidate = Path(root or Path.cwd()) / ATTESTIGNORE
    return [candidate] if candidate.exists() or candidate.is_symlink() else []
