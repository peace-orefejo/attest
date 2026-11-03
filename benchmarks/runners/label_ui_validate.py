"""Check labels sent from the labelling page before they are written to a label file.

Partial work is allowed: a label, the confidence or the rationale may stay blank, and the file
then counts as unfinished exactly as a hand-edited one would. Whatever is filled in is checked
against the existing `Annotation` model, by validating a copy whose blanks hold placeholders.
"""

from __future__ import annotations

from typing import Any, get_args

from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails

from bench_annotations import Annotation, Confidence
from bench_cases import LABELS, CheckName
from bench_template import LABEL_FIELDS, label_shape

EDITABLE = ("labels", "confidence", "ambiguous", "rationale")
MAX_RATIONALE = 5000


class Checked(BaseModel):
    """The label file to write, or why the submitted labels can't be written."""

    data: dict[str, Any] | None = None
    errors: list[str] = []


def check_submission(raw: dict[str, Any], submitted: object) -> Checked:
    """`raw` (the label file on disk) updated with the submitted labels, or the errors."""
    if not isinstance(submitted, dict):
        return Checked(errors=["send the labels as a JSON object"])
    fields: dict[str, Any] = submitted  # pyright: ignore[reportUnknownVariableType]
    errors = _field_errors(fields, raw)
    if errors:
        return Checked(errors=errors)
    data = {**raw, **{key: fields[key] for key in EDITABLE}}
    try:
        Annotation.model_validate(_placeholders(data))
    except ValidationError as exc:
        return Checked(errors=[_describe(error) for error in exc.errors()])
    return Checked(data=data)


def _field_errors(fields: dict[str, Any], raw: dict[str, Any]) -> list[str]:
    errors = [f"missing field {key!r}" for key in EDITABLE if key not in fields]
    errors += [f"unknown field {key!r}" for key in fields if key not in EDITABLE]
    if errors:
        return errors
    if fields["confidence"] is not None and fields["confidence"] not in get_args(Confidence):
        errors.append("confidence is high, medium or low")
    if not isinstance(fields["ambiguous"], bool):
        errors.append("ambiguous is true or false")
    rationale = fields["rationale"]
    if not isinstance(rationale, str) or len(rationale) > MAX_RATIONALE:
        errors.append(f"the rationale is text of at most {MAX_RATIONALE} characters")
    if label_shape(fields["labels"]) != label_shape(raw.get("labels")):
        errors.append("the items to label don't match the label file; reload the case")
    else:
        errors += _label_errors(fields["labels"], raw.get("check"))
    return errors


def _label_errors(value: object, check: object) -> list[str]:
    if isinstance(value, list):
        entries: list[Any] = value  # pyright: ignore[reportUnknownVariableType]
        return [error for entry in entries for error in _label_errors(entry, check)]
    if not isinstance(value, dict):
        return []
    items: dict[str, Any] = value  # pyright: ignore[reportUnknownVariableType]
    errors: list[str] = []
    for key, item in items.items():
        if key in LABEL_FIELDS:
            allowed = _allowed(key, check)
            if item is not None and item not in allowed:
                errors.append(f"{item!r} isn't a {key}; choose one of {', '.join(allowed)}")
        else:
            errors += _label_errors(item, check)
    return errors


def _allowed(field: str, check: object) -> tuple[str, ...]:
    if field == "verdict":
        return LABELS["tool_use"]
    if field == "recovery":
        return LABELS["recovery"]
    checks: dict[str, tuple[str, ...]] = {name: LABELS[name] for name in get_args(CheckName)}
    return checks.get(str(check), ())


def _placeholders(data: dict[str, Any]) -> dict[str, Any]:
    """A copy with each blank filled by a valid stand-in, so only filled-in values are judged."""
    filled = dict(data)
    filled["labels"] = _fill(data["labels"], data.get("check"))
    filled["confidence"] = data["confidence"] or "low"
    filled["rationale"] = data["rationale"] if str(data["rationale"]).strip() else "-"
    return filled


def _fill(value: object, check: object) -> object:
    if isinstance(value, list):
        entries: list[Any] = value  # pyright: ignore[reportUnknownVariableType]
        return [_fill(entry, check) for entry in entries]
    if not isinstance(value, dict):
        return value
    items: dict[str, Any] = value  # pyright: ignore[reportUnknownVariableType]
    return {
        key: (_allowed(key, check) or ("-",))[0]
        if key in LABEL_FIELDS and item is None
        else _fill(item, check)
        for key, item in items.items()
    }


def _describe(error: ErrorDetails) -> str:
    location = " > ".join(str(part) for part in error["loc"])
    return f"{location}: {error['msg']}" if location else error["msg"]
