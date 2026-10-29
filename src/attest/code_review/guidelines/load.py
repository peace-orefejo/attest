"""Load review guidelines from markdown files or text, or fall back to the built-in general standard."""

from __future__ import annotations

from collections.abc import Sequence
from importlib import resources
from pathlib import Path
from typing import Union

from .models import ReviewGuidelines
from .parse import MAX_RULES, parse_guidelines

GENERAL_NAME = "general standard"
GuidelinesInput = Union[None, str, Path, ReviewGuidelines, Sequence[Union[str, Path]]]


def general_guidelines() -> ReviewGuidelines:
    """The built-in standard used when no guidelines are given."""
    text = resources.files(__package__).joinpath("general.md").read_text(encoding="utf-8")
    return parse_guidelines(text, GENERAL_NAME).model_copy(update={"builtin": True})


_RULE_SUFFIXES = {".md", ".markdown", ".txt"}


def _is_path(value: str) -> bool:
    if "\n" in value:
        return False
    path = Path(value).expanduser()
    if path.is_file():
        return True
    return " " not in value.strip() and path.suffix.lower() in _RULE_SUFFIXES


def _one(value: str | Path) -> ReviewGuidelines:
    if isinstance(value, Path) or _is_path(value):
        path = Path(value).expanduser()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Could not read guidelines file {path}: {exc}") from exc
        return parse_guidelines(text, path.name)
    return parse_guidelines(value)


def _merge(parts: list[ReviewGuidelines]) -> ReviewGuidelines:
    rules = [rule for part in parts for rule in part.rules][:MAX_RULES]
    numbered = [rule.model_copy(update={"id": f"G{i}"}) for i, rule in enumerate(rules, 1)]
    return ReviewGuidelines(name=", ".join(part.name for part in parts), rules=numbered)


def load_guidelines(value: GuidelinesInput = None) -> ReviewGuidelines:
    """Resolve guidelines from a path, markdown text, a list of paths, or None for the general standard."""
    if value is None:
        return general_guidelines()
    if isinstance(value, ReviewGuidelines):
        return value
    if isinstance(value, (str, Path)):
        return _one(value)
    parts = [_one(item) for item in value]
    if not parts:
        return general_guidelines()
    return parts[0] if len(parts) == 1 else _merge(parts)
