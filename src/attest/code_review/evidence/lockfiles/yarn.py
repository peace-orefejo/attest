"""Version changes from a yarn.lock diff, classic v1 and berry."""

from __future__ import annotations

import re

from .base import VersionChange, collect_entries, pair_changes

_VERSION = re.compile(r'^  version:? "?(?P<version>[^"\s]+)"?\s*$')
_SHAPE = re.compile(r"^(#|\s+\S|\S.*:\s*$)")


def _name_of(text: str) -> str | None:
    if not text or text[0].isspace() or text.startswith("#") or not text.rstrip().endswith(":"):
        return None
    descriptor = text.rstrip()[:-1].split(",")[0].strip().strip('"')
    split = descriptor.find("@", 1)
    return descriptor[:split] if split > 0 else ""


def _version_of(text: str) -> str | None:
    match = _VERSION.match(text)
    if match is None or "use.local" in match.group("version"):
        return None
    return match.group("version")


def _shape_of(text: str) -> bool:
    return bool(_SHAPE.match(text))


def parse(diff_text: str) -> list[VersionChange]:
    """Return the package version changes in a yarn.lock diff."""
    removed, added = collect_entries(
        diff_text, name_of=_name_of, version_of=_version_of, shape_of=_shape_of
    )
    return pair_changes(removed, added)
