from __future__ import annotations

from pathlib import Path

from ...checks.role import check_role_adherence
from ..context import llm_context, require_key
from ..json_output import json_command
from ..options import MODEL_OPTION, PROVIDER_OPTION, REASONING_OPTION, require_reasoning
from ..single_check import run_single_check


@json_command("role")
def role(
    path: Path,
    provider: str = PROVIDER_OPTION,
    model: str | None = MODEL_OPTION,
    reasoning: str = REASONING_OPTION,
) -> None:
    """Judge whether the agent stayed within its system-prompt-defined role (needs a key)."""
    policy = require_reasoning(reasoning)
    require_key(provider)
    with llm_context(provider, model, reasoning=policy):
        run_single_check("role", path, check_role_adherence)
