from __future__ import annotations

from functools import partial
from pathlib import Path

import typer

from ...checks.tool_use import check_tool_use
from ..context import llm_context, require_key
from ..json_output import json_command
from ..options import MODEL_OPTION, PROVIDER_OPTION
from ..single_check import run_single_check


@json_command("tools")
def tools(
    path: Path,
    appropriate: bool = typer.Option(
        False, "--appropriate", help="Also run the LLM tool-choice check (needs a key)."
    ),
    check_answer: bool = typer.Option(
        False,
        "--check-answer",
        help="Ask a model whether the final answer reports unrecovered tool errors (needs a key).",
    ),
    provider: str = PROVIDER_OPTION,
    model: str | None = MODEL_OPTION,
) -> None:
    """Tool-use correctness only — deterministic, NO API key (unless --appropriate/--check-answer).

    --appropriate also checks the final answer for unrecovered tool errors.
    """
    uses_model = appropriate or check_answer
    if uses_model:
        require_key(provider)
    with llm_context(provider, model, enabled=uses_model):
        check = partial(check_tool_use, appropriate=appropriate, check_answer=uses_model)
        run_single_check("tools", path, check)
