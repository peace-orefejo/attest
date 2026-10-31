from __future__ import annotations

import typer

from ...providers import list_models, providers, resolve_key
from ..json_output import ModelList, emit, json_command


@json_command("models")
def models(
    provider: str = typer.Argument(..., help=f"One of: {', '.join(providers())}."),
) -> None:
    """List a provider's models — live if its key is set, otherwise the curated shortlist."""
    source = "live" if resolve_key(provider) else "curated"
    emit("models", ModelList(provider=provider, source=source, models=list_models(provider)))
