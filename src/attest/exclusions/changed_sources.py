"""Find exclusion pattern files that a change set edits, so a change can't hide itself."""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence

from ..utils.ignore_paths import split_path

_DIFF_SIDES = ("a", "b")


def changed_sources(sources: Sequence[str], changed: Iterable[str]) -> list[str]:
    """The pattern files among `sources` that one of the `changed` paths may edit.

    attest can't know where the repository starts, so a source counts as edited when its
    absolute path, as given or with symlinks resolved, ends with a changed path, compared on
    whole segments and case-insensitively. This fails safe: it also matches a same-named file
    at the same depth below another directory.
    """
    if not sources:
        return []
    suffixes = _changed_suffixes(changed)
    if not suffixes:
        return []
    return [source for source in sources if _edited(source, suffixes)]


def _edited(source: str, suffixes: set[tuple[str, ...]]) -> bool:
    for form in (os.path.abspath(source), _resolved(source)):
        if form is None:
            continue
        parts = _parts(form)
        if any(parts[-len(suffix) :] == suffix for suffix in suffixes if len(suffix) <= len(parts)):
            return True
    return False


def _changed_suffixes(changed: Iterable[str]) -> set[tuple[str, ...]]:
    suffixes: set[tuple[str, ...]] = set()
    for path in changed:
        parts = _parts(path)
        if not parts:
            continue
        suffixes.add(parts)
        if len(parts) > 1 and parts[0] in _DIFF_SIDES:
            suffixes.add(parts[1:])
    return suffixes


def _parts(path: str) -> tuple[str, ...]:
    return tuple(part.casefold() for part in split_path(path).parts)


def _resolved(path: str) -> str | None:
    try:
        return os.path.realpath(path)
    except (OSError, ValueError):
        return None
