from __future__ import annotations

from pathlib import Path

from ...checks.role import check_role_adherence
from ..context import llm_context, require_key
from ..options import JSON_OPTION, MODEL_OPTION, PROVIDER_OPTION
from ..single_check import run_single_check


def role(
    path: Path,
    provider: str = PROVIDER_OPTION,
    model: str | None = MODEL_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Judge whether the agent stayed within its system-prompt-defined role (needs a key)."""
    require_key(provider)
    with llm_context(provider, model):
        run_single_check(path, check_role_adherence, json_output=json_output)
