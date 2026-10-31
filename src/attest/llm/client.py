"""The provider-bound client used by every judge call in the current context."""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from contextvars import ContextVar
from functools import lru_cache

from ..providers import DEFAULT_PROVIDER, build_client
from .protocol import LLMClient

_active_client: ContextVar[LLMClient | None] = ContextVar("attest_client", default=None)


@lru_cache(maxsize=1)
def default_client() -> LLMClient:
    return build_client(DEFAULT_PROVIDER)


def resolve_client() -> LLMClient:
    return _active_client.get() or default_client()


def has_active_client() -> bool:
    """Whether a client was scoped with `using`, so a judge call won't fall back to the default."""
    return _active_client.get() is not None


@contextlib.contextmanager
def using(client: LLMClient) -> Generator[None]:
    """Run the enclosed calls against a specific provider-bound client."""
    token = _active_client.set(client)
    try:
        yield
    finally:
        _active_client.reset(token)
