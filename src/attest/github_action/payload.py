"""Typed reads from GitHub's JSON, which may lack any field or hold the wrong type."""

from __future__ import annotations

from typing import Any, cast

Json = dict[str, Any]


def as_obj(value: object) -> Json:
    """`value` when it is a JSON object, else an empty one."""
    return cast(Json, value) if isinstance(value, dict) else {}


def obj(data: Json, key: str) -> Json:
    """`data[key]` when it is an object, else an empty one."""
    return as_obj(data.get(key))


def items(data: object) -> list[Json]:
    """The objects in a JSON list, skipping anything else."""
    if not isinstance(data, list):
        return []
    found = (as_obj(item) for item in cast(list[object], data))
    return [item for item in found if item]


def text(data: Json, key: str) -> str:
    """`data[key]` when it is a string, else ""."""
    value: object = data.get(key)
    return value if isinstance(value, str) else ""


def optional_text(data: Json, key: str) -> str | None:
    """`data[key]` when it is a string, else None."""
    value: object = data.get(key)
    return value if isinstance(value, str) else None


def integer(data: Json, key: str) -> int | None:
    """`data[key]` when it is an integer (not a bool), else None."""
    value: object = data.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None
