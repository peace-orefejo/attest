"""Version changes from a go.sum diff."""

from __future__ import annotations

import re

from .base import Entry, VersionChange, collect_entries, pair_changes

_LINE = re.compile(r"^(?P<module>\S+) (?P<version>v[^\s/]+)(?:/go\.mod)? h1:\S+$")


def _entry_of(text: str) -> Entry | None:
    match = _LINE.match(text.strip())
    return (match.group("module"), match.group("version")) if match else None


def parse(diff_text: str) -> list[VersionChange]:
    """Return the module version changes in a go.sum diff."""
    removed, added = collect_entries(diff_text, entry_of=_entry_of)
    return pair_changes(removed, added)
