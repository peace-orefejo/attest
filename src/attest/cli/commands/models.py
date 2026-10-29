from __future__ import annotations

import typer

from ...providers import list_models, providers, resolve_key


def models(
    provider: str = typer.Argument(..., help=f"One of: {', '.join(providers())}."),
) -> None:
    """List a provider's models — live if its key is set, otherwise the curated shortlist."""
    source = "live" if resolve_key(provider) else "curated"
    typer.echo(f"{provider} models ({source}):")
    for name in list_models(provider):
        typer.echo(f"  {name}")
