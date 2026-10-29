from __future__ import annotations

import csv
import json
from collections.abc import Iterable


def _json_parts(raw: bytes) -> Iterable[tuple[str, str]]:
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


def _csv_parts(raw: bytes, delimiter: str, max_chars: int) -> Iterable[tuple[str, str]]:
    """Parse the default CSV dialect without mutating csv.field_size_limit globally."""
    text = raw.decode("utf-8", errors="replace")

    def parts() -> Iterable[tuple[str, str]]:
        row = column = index = 0
        field: list[str] = []
        in_quotes = False
        field_limit = max(0, max_chars) + 1

        def value() -> str:
            return "".join(field)

        while index < len(text):
            char = text[index]
            if in_quotes:
                if char == '"':
                    if index + 1 < len(text) and text[index + 1] == '"':
                        if len(field) < field_limit:
                            field.append('"')
                        index += 2
                        continue
                    in_quotes = False
                elif len(field) < field_limit:
                    field.append(char)
            elif char == '"' and not field:
                in_quotes = True
            elif char == delimiter:
                cell = value()
                if cell.strip():
                    yield (f"csv.row[{row}].cell[{column}]", cell)
                field.clear()
                column += 1
            elif char in "\r\n":
                cell = value()
                if cell.strip():
                    yield (f"csv.row[{row}].cell[{column}]", cell)
                field.clear()
                row += 1
                column = 0
                if char == "\r" and index + 1 < len(text) and text[index + 1] == "\n":
                    index += 1
            elif len(field) < field_limit:
                field.append(char)
            index += 1

        if in_quotes:
            raise csv.Error("unexpected end of data")
        cell = value()
        if cell.strip():
            yield (f"csv.row[{row}].cell[{column}]", cell)

    return parts()
