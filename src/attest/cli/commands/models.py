from __future__ import annotations

import typer

from ...providers import list_models, providers, resolve_key
from ..options import JSON_OPTION
from ..rendering import emit_json


def models(
    provider: str = typer.Argument(..., help=f"One of: {', '.join(providers())}."),
    json_output: bool = JSON_OPTION,
) -> None:
    """List a provider's models — live if its key is set, otherwise the curated shortlist."""
    source = "live" if resolve_key(provider) else "curated"
    names = list_models(provider)
    if json_output:
        emit_json({"provider": provider, "source": source, "models": names})
        return
    typer.echo(f"{provider} models ({source}):")
    for name in names:
        typer.echo(f"  {name}")
