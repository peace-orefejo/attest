"""A path as written and with symlinks resolved, so a link to an excluded file is excluded too."""

from __future__ import annotations

import os
from pathlib import Path, PurePath


def cwd_roots() -> list[Path]:
    """The current directory as given and with symlinks resolved."""
    cwd = Path.cwd()
    return list(dict.fromkeys([cwd, cwd.resolve()]))


def path_forms(path: str, roots: list[Path] | None = None) -> list[str]:
    """`path` as written, then with symlinks resolved, made relative to the current directory.

    The resolved form is relative when it lies inside the current directory (or `roots`), and
    absolute otherwise. A path that can't be resolved is matched as written only.
    """
    forms = [within_cwd(path, roots)]
    resolved = _resolved(path)
    if resolved is not None:
        forms.append(within_cwd(resolved, roots))
    return list(dict.fromkeys(forms))


def within_cwd(path: str, roots: list[Path] | None = None) -> str:
    """An absolute path inside the current directory made relative to it, else unchanged."""
    if not PurePath(path).is_absolute():
        return path
    absolute = os.path.normpath(path)
    for root in roots if roots is not None else cwd_roots():
        base = str(root)
        if absolute == base:
            return "."
        prefix = base if base.endswith(os.sep) else base + os.sep
        if absolute.startswith(prefix):
            return PurePath(absolute[len(prefix) :]).as_posix()
    return path


def _resolved(path: str) -> str | None:
    try:
        return os.path.realpath(path) if _may_resolve(path) else None
    except (OSError, ValueError):
        return None


def _may_resolve(path: str) -> bool:
    """False for a relative path, without `..`, whose first segment doesn't exist: no link in
    it can resolve, so the file-system lookups are skipped."""
    parts = path.split(os.sep)
    if os.path.isabs(path) or ".." in parts:
        return True
    return os.path.lexists(parts[0] or ".")
