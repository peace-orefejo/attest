from __future__ import annotations

from pathlib import Path

import typer
from pydantic import BaseModel, ValidationError

from ..trajectory import Trajectory


class _SourceLine(BaseModel):
    number: int
    text: str


def load_trajectories(path: Path) -> list[Trajectory]:
    raw = _read(path)
    return [_parse(path, line) for line in _source_lines(path, raw) if line.text.strip()]


def _read(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise typer.BadParameter(f"Could not read trajectory file {path}: {exc}") from exc
    if not raw:
        raise typer.BadParameter(f"Trajectory file {path} is empty.")
    return raw


def _is_single_document(path: Path) -> bool:
    return path.suffix.lower() == ".json"


def _source_lines(path: Path, raw: str) -> list[_SourceLine]:
    if _is_single_document(path):
        return [_SourceLine(number=1, text=raw)]
    return [_SourceLine(number=n, text=text) for n, text in enumerate(raw.splitlines(), 1)]


def _parse(path: Path, line: _SourceLine) -> Trajectory:
    try:
        return Trajectory.model_validate_json(line.text)
    except (ValidationError, ValueError) as exc:
        location = f"{path}" if _is_single_document(path) else f"{path}, line {line.number}"
        raise typer.BadParameter(f"Invalid trajectory in {location}: {_detail(exc)}") from exc


def _detail(exc: ValueError) -> str:
    if isinstance(exc, ValidationError):
        return exc.errors()[0]["msg"]
    return str(exc)
