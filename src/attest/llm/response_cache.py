"""Context-scoped memoization of judge responses, keyed by the exact prompt and sample."""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections.abc import Iterator, MutableMapping
from contextvars import ContextVar

from pydantic import BaseModel

ResponseStore = MutableMapping[str, BaseModel | dict[str, object]]

response_cache: ContextVar[ResponseStore | None] = ContextVar("attest_response_cache", default=None)


@contextlib.contextmanager
def using_cache(store: ResponseStore | None) -> Iterator[None]:
    """Memoize identical judge calls into `store`, so re-evaluating a run is free.

    The key includes the sample index, so `vote`'s independent samples stay distinct within a
    run while a later identical run reuses them. The store is model-scoped by the caller: one
    provider-bound client per store, so the model need not appear in the key.
    """
    token = response_cache.set(store)
    try:
        yield
    finally:
        response_cache.reset(token)


def cache_key(system: str, user: str, output: type[BaseModel], sample: int, prefix: str) -> str:
    parts: list[str | int] = [system, user, output.__name__, sample]
    if prefix:
        parts.append(prefix)
    payload = json.dumps(parts, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()
