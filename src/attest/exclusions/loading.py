"""Read exclusion patterns from `.attestignore`-style files and combine them with direct ones."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from .rules import ExclusionError, Exclusions

ATTESTIGNORE = ".attestignore"
MAX_PATTERN_FILE_BYTES = 1_048_576

PathInput = str | os.PathLike[str]

ExclusionsInput = Exclusions | os.PathLike[str] | Sequence[str] | None
"""An `Exclusions`, a list of patterns, a path to a pattern file, or None for no exclusions."""


def as_exclusions(value: ExclusionsInput) -> Exclusions:
    """Turn any accepted exclusion input into `Exclusions`.

    A `Path` (any `os.PathLike`) is read as a pattern file. A bare string is refused with
    `TypeError`: it would be ambiguous between one pattern and a file name, so pass
    `["*.env"]` for one pattern or `Path("team.attestignore")` for a file.
    """
    if value is None:
        return Exclusions()
    if isinstance(value, Exclusions):
        return value
    if isinstance(value, os.PathLike):
        return load_exclusions(files=[value])
    if isinstance(value, str):
        raise TypeError(
            f"exclude={value!r} is a bare string. Pass a list of patterns, such as "
            f"[{value!r}], or a Path to read patterns from a file, such as Path({value!r})."
        )
    return Exclusions(patterns=tuple(value))


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
