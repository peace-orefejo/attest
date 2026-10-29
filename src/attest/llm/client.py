"""The provider-bound instructor client used by every judge call in the current context."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar
from functools import lru_cache

import instructor

from ..providers import DEFAULT_PROVIDER, build_client

_active_client: ContextVar[instructor.Instructor | None] = ContextVar("attest_client", default=None)


@lru_cache(maxsize=1)
def default_client() -> instructor.Instructor:
    return build_client(DEFAULT_PROVIDER)


def resolve_client() -> instructor.Instructor:
    return _active_client.get() or default_client()


@contextlib.contextmanager
def using(client: instructor.Instructor) -> Iterator[None]:
    """Run the enclosed calls against a specific provider-bound client."""
    token = _active_client.set(client)
    try:
        yield
    finally:
        _active_client.reset(token)
