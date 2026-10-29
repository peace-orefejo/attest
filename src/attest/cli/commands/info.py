"""Small utility commands: stats and models."""

from __future__ import annotations

import typer

from ...core import wilson_interval
from ...core.llm import list_models, providers, resolve_key
from ..app import JSON_OPT, app
from ..common import emit_json


@app.command()
def stats(successes: int, n: int, json_output: bool = JSON_OPT) -> None:
    """Report a pass rate with a Wilson 95% confidence interval."""
    interval = wilson_interval(successes, n)
    if json_output:
        emit_json(interval.model_dump(mode="json"))
        return
    typer.echo(interval.pct())


@app.command()
def models(
    provider: str = typer.Argument(..., help=f"One of: {', '.join(providers())}."),
    json_output: bool = JSON_OPT,
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
