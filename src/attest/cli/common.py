"""Shared CLI plumbing: API keys, the model context, loading trajectories and printing results."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console, RenderableType
from rich.text import Text

from ..core import Trajectory
from ..core.llm import build_client, resolve_key, using
from ..display import Result, strip_trailing, view


def require_key(provider: str) -> None:
    if not resolve_key(provider):
        typer.echo(f"Set a {provider} API key (its env var) in the workspace .env to run this.")
        raise typer.Exit(code=1)


def llm_ctx(provider: str, model: str | None):
    return using(build_client(provider, model))


def read_text(path: Path, what: str) -> str:
    try:
        raw = path.read_text().strip()
    except OSError as exc:
        raise typer.BadParameter(f"Could not read {what} file {path}: {exc}") from exc
    if not raw:
        raise typer.BadParameter(f"{what.capitalize()} file {path} is empty.")
    return raw


def load_trajectories(path: Path) -> list[Trajectory]:
    raw = read_text(path, "trajectory")
    is_json = path.suffix.lower() == ".json"
    lines = [(1, raw)] if is_json else list(enumerate(raw.splitlines(), 1))
    trajectories: list[Trajectory] = []
    for line_number, line in lines:
        if not line.strip():
            continue
        try:
            trajectories.append(Trajectory.model_validate_json(line))
        except (ValidationError, ValueError) as exc:
            location = f"{path}" if is_json else f"{path}, line {line_number}"
            detail = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
            raise typer.BadParameter(f"Invalid trajectory in {location}: {detail}") from exc
    return trajectories


def emit_json(value) -> None:
    typer.echo(json.dumps(value, indent=2))


def console() -> Console:
    return Console(highlight=False)


def print_view(*renderables: RenderableType) -> None:
    out = console()
    with out.capture() as captured:
        for renderable in renderables:
            out.print(renderable)
    typer.echo(strip_trailing(captured.get()), nl=False)


def print_results(items: list[tuple[str, Result]], footer: str | None = None) -> None:
    parts: list[RenderableType] = []
    for position, (title, result) in enumerate(items):
        if position:
            parts.append(Text(""))
        parts.append(view(result, title=title))
    if footer:
        parts += [Text(""), Text(footer, style="bold")]
    print_view(*parts)
