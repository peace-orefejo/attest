"""Load review guidelines from markdown files or text, or fall back to the general standard."""

from __future__ import annotations

from collections.abc import Sequence
from importlib import resources
from pathlib import Path
from typing import TypeAlias

from .models import ReviewGuidelines
from .parse import MAX_GUIDELINES_CHARS, MAX_RULES, parse_guidelines

GENERAL_NAME = "general standard"
GuidelinesInput: TypeAlias = str | Path | ReviewGuidelines | Sequence[str | Path] | None

_RULE_SUFFIXES = {".md", ".markdown", ".txt"}
_PACKAGE = __name__.rpartition(".")[0]


def general_guidelines() -> ReviewGuidelines:
    """The built-in standard used when no guidelines are given."""
    text = resources.files(_PACKAGE).joinpath("general.md").read_text(encoding="utf-8")
    return parse_guidelines(text, GENERAL_NAME).model_copy(update={"builtin": True})


def load_guidelines(value: GuidelinesInput = None) -> ReviewGuidelines:
    """Resolve guidelines from a path, markdown text, a list of paths, or None for the default."""
    if value is None:
        return general_guidelines()
    if isinstance(value, ReviewGuidelines):
        return value
    if isinstance(value, str | Path):
        return _one(value)
    parts = [_one(item) for item in value]
    if not parts:
        return general_guidelines()
    return parts[0] if len(parts) == 1 else _merge(parts)


def _one(value: str | Path) -> ReviewGuidelines:
    if isinstance(value, Path) or _is_path(value):
        path = Path(value).expanduser()
        return parse_guidelines(_read(path), path.name)
    return parse_guidelines(value)


def _read(path: Path) -> str:
    try:
        with path.open(encoding="utf-8") as handle:
            text = handle.read(MAX_GUIDELINES_CHARS + 1)
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Could not read guidelines file {path}: {exc}") from exc
    return text


def _is_path(value: str) -> bool:
    if "\n" in value:
        return False
    path = Path(value).expanduser()
    if _exists(path):
        return True
    return " " not in value.strip() and path.suffix.lower() in _RULE_SUFFIXES


def _exists(path: Path) -> bool:
    try:
        return path.is_file()
    except (OSError, ValueError):
        return False


def _merge(parts: list[ReviewGuidelines]) -> ReviewGuidelines:
    rules = [rule for part in parts for rule in part.rules][:MAX_RULES]
    numbered = [rule.model_copy(update={"id": f"G{i}"}) for i, rule in enumerate(rules, 1)]
    return ReviewGuidelines(name=", ".join(part.name for part in parts), rules=numbered)
