"""Find exclusion pattern files that a change set edits, so a change can't hide itself."""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from pathlib import Path

from ..utils.ignore_paths import split_path

_DIFF_SIDES = ("a", "b")


def changed_sources(
    sources: Sequence[str], changed: Iterable[str], *, root: str | os.PathLike[str] | None = None
) -> list[str]:
    """The pattern files among `sources` that one of the `changed` repo-relative paths edits.

    The repository root may be `root` (the current directory by default) or any directory
    above it, so each changed path is tried against all of them. A source matches by its
    path as given or with symlinks resolved, compared case-insensitively to fail safe.
    """
    if not sources:
        return []
    start = Path(os.path.abspath(root or Path.cwd()))
    bases = [start, *start.parents]
    edited: list[str] = []
    candidates = {_key(path) for path in _changed_paths(changed, bases)}
    for source in sources:
        forms = {_key(os.path.abspath(source)), _key(os.path.realpath(source))}
        if forms & candidates:
            edited.append(source)
    return edited


def _changed_paths(changed: Iterable[str], bases: list[Path]) -> list[str]:
    paths: list[str] = []
    for path in changed:
        split = split_path(path)
        if not split.parts or split.floating:
            continue
        forms = [split.parts]
        if len(split.parts) > 1 and split.parts[0] in _DIFF_SIDES:
            forms.append(split.parts[1:])
        for parts in forms:
            paths.extend(os.path.join(base, *parts) for base in bases)
    return paths


def _key(path: str) -> str:
    return os.path.normpath(path).casefold()
