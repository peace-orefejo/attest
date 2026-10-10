"""The client that model calls use: a per-context override, else a lazily built default."""

from __future__ import annotations

import contextlib
from contextvars import ContextVar
from functools import lru_cache
from typing import Iterator

from .clients import LLMClient, build_client
from .providers import DEFAULT_PROVIDER

_active_client: ContextVar[LLMClient | None] = ContextVar(
    "attest_client", default=None
)


@lru_cache(maxsize=1)
def _default_client() -> LLMClient:
    return build_client(DEFAULT_PROVIDER)


def _resolve_client() -> LLMClient:
    return _active_client.get() or _default_client()


@contextlib.contextmanager
def using(client: LLMClient) -> Iterator[None]:
    """Run the enclosed calls against a specific provider-bound client."""
    token = _active_client.set(client)
    try:
        yield
    finally:
        _active_client.reset(token)
