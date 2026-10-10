"""JSON string values keyed by their JSONPath-like location."""

from __future__ import annotations

import json
from typing import Iterable


def json_parts(raw: bytes) -> Iterable[tuple[str, str]]:
    value = json.loads(raw)
    def walk(item, path: str) -> Iterable[tuple[str, str]]:
        if isinstance(item, dict):
            for key, child in item.items():
                yield from walk(child, f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                yield from walk(child, f"{path}[{index}]")
        elif isinstance(item, str):
            yield (f"json{path}", item)
    return walk(value, "$")
