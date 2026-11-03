from __future__ import annotations

import contextlib
from collections.abc import Generator

from ..llm import ReasoningPolicy, using, using_reasoning
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


@contextlib.contextmanager
def llm_context(
    provider: str,
    model: str | None,
    *,
    enabled: bool = True,
    reasoning: ReasoningPolicy | None = None,
) -> Generator[None]:
    if not enabled:
        yield
        return
    with using(build_client(provider, model)), using_reasoning(reasoning or ReasoningPolicy()):
        yield
