from __future__ import annotations

from typing import TypeGuard

from pypdf.generic import DictionaryObject, PdfObject, StreamObject


def resolve(value: object) -> object:
    return value.get_object() if isinstance(value, PdfObject) else value


def require_dictionary(value: object) -> DictionaryObject:
    if not isinstance(value, DictionaryObject):
        raise ValueError(f"Malformed PDF: expected a dictionary, got {type(value).__name__}")
    return value


def require_stream(value: object) -> StreamObject:
    if not isinstance(value, StreamObject):
        raise ValueError(f"Malformed PDF: expected a stream, got {type(value).__name__}")
    return value


def as_object_list(value: object) -> list[object] | None:
    return value if _is_list(value) else None


def _is_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)
