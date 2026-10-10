"""Version changes from a package-lock.json (lockfile v2 and v3) diff."""

from __future__ import annotations

import re

from .base import VersionChange, collect_entries, pair_changes

_KEY = re.compile(r'^\s*"(?P<key>[^"]*)":\s*\{\s*$')
_VERSION = re.compile(r'^\s*"version":\s*"(?P<version>[^"]+)"')
_SHAPE = re.compile(r'^\s*("|[{}\[\]])')
_RESERVED = frozenset({
    "dependencies", "devDependencies", "optionalDependencies", "peerDependencies",
    "peerDependenciesMeta", "bundleDependencies", "requires", "engines", "bin", "funding",
    "packages", "workspaces", "overrides", "directories", "scripts", "repository",
    "cpu", "os", "libc",
})


def _name_of(text: str) -> str | None:
    match = _KEY.match(text)
    if match is None:
        return None
    key = match.group("key")
    if key in _RESERVED:
        return None
    if "node_modules/" in key:
        return key.rsplit("node_modules/", 1)[1]
    return key


def _version_of(text: str) -> str | None:
    match = _VERSION.match(text)
    return match.group("version") if match else None


def parse(diff_text: str) -> list[VersionChange]:
    """Return the package version changes in a package-lock.json diff."""
    removed, added = collect_entries(
        diff_text,
        name_of=_name_of,
        version_of=_version_of,
        shape_of=lambda text: bool(_SHAPE.match(text)),
    )
    return pair_changes(removed, added)
