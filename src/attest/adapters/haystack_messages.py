"""Read Haystack `ChatMessage` objects, or their `to_dict()` form, into plain models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..utils.json_types import JsonObject
from .guards import is_object_dict, is_object_list


class HaystackCall(BaseModel):
    tool_name: str
    arguments: JsonObject = Field(default_factory=dict)
    id: str | None = None


class HaystackResult(BaseModel):
    result: str
    origin_id: str | None = None


class HaystackMessage(BaseModel):
    role: str
    text: str | None = None
    tool_calls: list[HaystackCall] = Field(default_factory=list[HaystackCall])
    tool_call_results: list[HaystackResult] = Field(default_factory=list[HaystackResult])


def read_message(message: object) -> HaystackMessage:
    if is_object_dict(message):
        return _read_dict(message)
    return HaystackMessage(
        role=_role(getattr(message, "role", None)),
        text=_text_or_none(getattr(message, "text", None)),
        tool_calls=[_read_call(c) for c in _list_attr(message, "tool_calls")],
        tool_call_results=[_read_result(r) for r in _results(message)],
    )


def _read_dict(message: dict[str, object]) -> HaystackMessage:
    content = message.get("content")
    parts = content if is_object_list(content) else [{"text": content}]
    texts = [t for p in parts if (t := _text_or_none(_field(p, "text")))]
    return HaystackMessage(
        role=_role(message.get("role")),
        text=texts[0] if texts else None,
        tool_calls=[_read_call(c) for p in parts if (c := _field(p, "tool_call")) is not None],
        tool_call_results=[
            _read_result(r) for p in parts if (r := _field(p, "tool_call_result")) is not None
        ],
    )


def _results(message: object) -> list[object]:
    results = _list_attr(message, "tool_call_results")
    if results:
        return results
    single: object = getattr(message, "tool_call_result", None)
    return [] if single is None else [single]


def _read_call(call: object) -> HaystackCall:
    arguments = _field(call, "arguments")
    return HaystackCall(
        tool_name=_text_or_none(_field(call, "tool_name")) or "tool",
        arguments=arguments if is_object_dict(arguments) else {},
        id=_text_or_none(_field(call, "id")),
    )


def _read_result(result: object) -> HaystackResult:
    origin = _field(result, "origin")
    return HaystackResult(
        result=_result_text(_field(result, "result")),
        origin_id=None if origin is None else _text_or_none(_field(origin, "id")),
    )


def _result_text(result: object) -> str:
    if isinstance(result, str):
        return result
    if is_object_list(result):
        texts = [_text_or_none(_field(part, "text")) for part in result]
        return "\n".join(t for t in texts if t)
    return "" if result is None else str(result)


def _role(role: object) -> str:
    value: object = getattr(role, "value", role)
    return value.lower() if isinstance(value, str) else ""


def _field(obj: object, name: str) -> object:
    if is_object_dict(obj):
        return obj.get(name)
    return getattr(obj, name, None)


def _list_attr(obj: object, name: str) -> list[object]:
    value: object = getattr(obj, name, None)
    return value if is_object_list(value) else []


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
