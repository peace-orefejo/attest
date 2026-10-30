from __future__ import annotations

import contextlib
from contextlib import AbstractContextManager

import typer

from ..llm import using
from ..providers import build_client, resolve_key


def require_key(provider: str) -> None:
    if resolve_key(provider):
        return
    typer.echo(f"Set a {provider} API key (its env var) in the workspace .env to run this.")
    raise typer.Exit(code=1)


def llm_context(
    provider: str, model: str | None, *, enabled: bool = True
) -> AbstractContextManager[None]:
    if not enabled:
        return contextlib.nullcontext()
    return using(build_client(provider, model))
