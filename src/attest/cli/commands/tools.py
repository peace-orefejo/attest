from __future__ import annotations

from functools import partial
from pathlib import Path

import typer

from ...checks.tool_use import check_tool_use
from ..context import llm_context, require_key
from ..options import JSON_OPTION, MODEL_OPTION, PROVIDER_OPTION
from ..single_check import run_single_check


def tools(
    path: Path,
    appropriate: bool = typer.Option(
        False, "--appropriate", help="Also run the LLM tool-choice check (needs a key)."
    ),
    provider: str = PROVIDER_OPTION,
    model: str | None = MODEL_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Tool-use correctness only — deterministic, NO API key (unless --appropriate)."""
    if appropriate:
        require_key(provider)
    with llm_context(provider, model, enabled=appropriate):
        check = partial(check_tool_use, appropriate=appropriate)
        run_single_check(path, check, json_output=json_output)
