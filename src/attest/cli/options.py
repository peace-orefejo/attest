from __future__ import annotations

import typer

from ..checks.verify import MAX_CLAIMS
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
KIND_OPTION = typer.Option(
    "factual",
    "--kind",
    help=(
        "Answer type: 'factual' (default), 'plan' (judge fidelity to the plan), "
        "'code' (judge against diffs and source), or 'auto' (pick factual or code "
        "from the evidence)."
    ),
)
MAX_CLAIMS_OPTION = typer.Option(
    MAX_CLAIMS,
    "--max-claims",
    help="Check at most this many claims per answer. An answer with more never passes, "
    "since the rest go unchecked.",
)


def require_max_claims(value: int) -> int:
    """`--max-claims`, rejected as invalid input when it is negative."""
    if value < 0:
        raise typer.BadParameter(f"must be 0 or more, not {value}.", param_hint="--max-claims")
    return value
