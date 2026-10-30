"""Type guards for narrowing duck-typed framework objects without importing the framework."""

from __future__ import annotations

from typing import TypeGuard


def is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def is_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def str_attr(obj: object, name: str) -> str | None:
    value: object = getattr(obj, name, None)
    return value if isinstance(value, str) else None
