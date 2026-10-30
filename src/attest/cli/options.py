from __future__ import annotations

import typer

from ..providers import DEFAULT_PROVIDER

PROVIDER_OPTION = typer.Option(
    DEFAULT_PROVIDER,
    "--provider",
    "-p",
    help="LLM provider: anthropic (default), openai, or gemini.",
)
MODEL_OPTION = typer.Option(
    None, "--model", "-m", help="Model id; defaults to a sensible model for the provider."
)
JSON_OPTION = typer.Option(False, "--json", help="Emit machine-readable JSON.")
