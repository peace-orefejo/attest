from __future__ import annotations

import typer

from ..core.llm import DEFAULT_PROVIDER, load_env

load_env()
app = typer.Typer(help="Evidence-grounded evaluation for AI agent trajectories.")

PROVIDER_OPT = typer.Option(DEFAULT_PROVIDER, "--provider", "-p",
                            help="LLM provider: anthropic (default), openai, or gemini.")
MODEL_OPT = typer.Option(None, "--model", "-m",
                         help="Model id; defaults to a sensible model for the provider.")
JSON_OPT = typer.Option(False, "--json", help="Emit machine-readable JSON.")
