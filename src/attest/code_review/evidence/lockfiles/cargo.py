"""Version changes from a Cargo.lock diff."""

from __future__ import annotations

import re

from .base import VersionChange, collect_entries, pair_changes

_NAME = re.compile(r'^name = "(?P<name>[^"]+)"')
_VERSION = re.compile(r'^version = "(?P<version>[^"]+)"')
_SHAPE = re.compile(r'^(\[|\s*[\w."-]+\s*=|\s*[\]"]|#|\s*$)')


def _name_of(text: str) -> str | None:
    if text.startswith("[[package]]"):
        return ""
    match = _NAME.match(text)
    return match.group("name") if match else None


def _version_of(text: str) -> str | None:
    match = _VERSION.match(text)
    return match.group("version") if match else None


def parse(diff_text: str) -> list[VersionChange]:
    """Return the crate version changes in a Cargo.lock diff."""
    removed, added = collect_entries(
        diff_text,
        name_of=_name_of,
        version_of=_version_of,
        shape_of=lambda text: bool(_SHAPE.match(text)),
    )
    return pair_changes(removed, added)
