"""Version changes from a pnpm-lock.yaml diff, lockfile v5 through v9."""

from __future__ import annotations

import re

from .base import Entry, VersionChange, collect_entries, pair_changes

_KEY = re.compile(r"""^ {2}['"]?(?P<id>[^\s'"]+)['"]?:\s*$""")
_SLASH_FORM = re.compile(r"^(?P<name>(?:@[^/]+/)?[^/@]+)/(?P<version>\d[^_/()]*)")
_AT_FORM = re.compile(r"^(?P<name>(?:@[^/@]+/)?[^/@]+)@(?P<version>[^()\s]+)")
_SHAPE = re.compile(r"""^\s*(-\s+)?(['"]?[^\s'"][^:]*['"]?:(\s|$)|-\s)""")


def _entry_of(text: str) -> Entry | None:
    match = _KEY.match(text)
    if match is None:
        return None
    package_id = match.group("id")
    if package_id.startswith("/"):
        slash = _SLASH_FORM.match(package_id[1:])
        if slash is not None:
            return slash.group("name"), slash.group("version")
        package_id = package_id[1:]
    at = _AT_FORM.match(package_id)
    return (at.group("name"), at.group("version")) if at else None


def parse(diff_text: str) -> list[VersionChange]:
    """Return the package version changes in a pnpm-lock.yaml diff."""
    removed, added = collect_entries(
        diff_text,
        entry_of=_entry_of,
        shape_of=lambda text: bool(_SHAPE.match(text)),
    )
    return pair_changes(removed, added)
