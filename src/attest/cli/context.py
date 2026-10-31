from __future__ import annotations

import contextlib
from contextlib import AbstractContextManager

from ..llm import using
from ..providers import build_client, resolve_key
from .json_output import EXIT_ERROR, CommandError


def require_key(provider: str) -> None:
    if resolve_key(provider):
        return
    raise CommandError(
        "missing_api_key",
        f"Set the {provider} API key (its env var) in the workspace .env to run this.",
        EXIT_ERROR,
    )


def llm_context(
    provider: str, model: str | None, *, enabled: bool = True
) -> AbstractContextManager[None]:
    if not enabled:
        return contextlib.nullcontext()
    return using(build_client(provider, model))
