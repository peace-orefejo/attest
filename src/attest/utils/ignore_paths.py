"""Split a path into the segments a gitignore-style matcher compares, resolving `.` and `..`."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

_DRIVE = re.compile(r"[A-Za-z]:(/|$)")


class PathParts(BaseModel):
    """A path's segments, and whether its root is unknown.

    A floating path (absolute, a Windows drive path, or one that climbs above its start with
    `..`) could sit anywhere in the repository, so it is matched as if it started at each of
    its segments.
    """

    model_config = ConfigDict(frozen=True)

    parts: tuple[str, ...]
    floating: bool = False


def split_path(path: str) -> PathParts:
    """Treat `\\` as `/`, collapse `//`, drop `.` and resolve `..` against earlier segments."""
    text = path.replace("\\", "/")
    floating = text.startswith("/") or _DRIVE.match(text) is not None
    parts: list[str] = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part != "..":
            parts.append(part)
        elif parts:
            parts.pop()
        else:
            floating = True
    return PathParts(parts=tuple(parts), floating=floating)


def normalize_path(path: str) -> str:
    """The path with forward slashes, no empty or `.` segments and `..` resolved."""
    return "/".join(split_path(path).parts)
