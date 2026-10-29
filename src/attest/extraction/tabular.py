from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from typing import TypeGuard

from .parts import ExtractedPart, ParsedParts


def json_parts(raw: bytes) -> ParsedParts:
    return ParsedParts(parts=_walk_json(json.loads(raw), "$"))


def _walk_json(item: object, path: str) -> Iterator[ExtractedPart]:
    if _is_json_object(item):
        for key, child in item.items():
            yield from _walk_json(child, f"{path}.{key}")
    elif _is_json_array(item):
        for index, child in enumerate(item):
            yield from _walk_json(child, f"{path}[{index}]")
    elif isinstance(item, str):
        yield ExtractedPart(source_kind=f"json{path}", text=item)


def _is_json_object(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _is_json_array(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def csv_parts(raw: bytes, delimiter: str, max_chars: int) -> ParsedParts:
    """Parse the default CSV dialect without mutating csv.field_size_limit globally."""
    text = raw.decode("utf-8", errors="replace")
    field_limit = max(0, max_chars) + 1
    return ParsedParts(parts=_csv_cells(text, delimiter, field_limit))


def _csv_cells(text: str, delimiter: str, field_limit: int) -> Iterator[ExtractedPart]:
    row = column = index = 0
    field: list[str] = []
    in_quotes = False
    while index < len(text):
        char = text[index]
        if in_quotes:
            if char == '"':
                if _next_char(text, index) == '"':
                    _append_bounded(field, '"', field_limit)
                    index += 2
                    continue
                in_quotes = False
            else:
                _append_bounded(field, char, field_limit)
        elif char == '"' and not field:
            in_quotes = True
        elif char == delimiter:
            yield from _cell_part(row, column, field)
            field.clear()
            column += 1
        elif char in "\r\n":
            yield from _cell_part(row, column, field)
            field.clear()
            row += 1
            column = 0
            if char == "\r" and _next_char(text, index) == "\n":
                index += 1
        else:
            _append_bounded(field, char, field_limit)
        index += 1

    if in_quotes:
        raise csv.Error("unexpected end of data")
    yield from _cell_part(row, column, field)


def _next_char(text: str, index: int) -> str:
    return text[index + 1 : index + 2]


def _append_bounded(field: list[str], char: str, field_limit: int) -> None:
    if len(field) < field_limit:
        field.append(char)


def _cell_part(row: int, column: int, field: list[str]) -> Iterator[ExtractedPart]:
    cell = "".join(field)
    if cell.strip():
        yield ExtractedPart(source_kind=f"csv.row[{row}].cell[{column}]", text=cell)
