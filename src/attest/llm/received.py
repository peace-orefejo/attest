"""Keep each raw response an instructor client receives, so a call that fails to parse still has
the billed response: instructor's parsers can fail before they record it (Gemini's tool mode
asserts on a cut-off answer)."""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from contextvars import ContextVar

_received: ContextVar[list[object] | None] = ContextVar("attest_received", default=None)


def listen(inner: object) -> None:
    """Hear every response `inner` (an instructor client) receives, before it is parsed."""
    on = getattr(inner, "on", None)
    if callable(on):
        on("completion:response", _keep)


@contextlib.contextmanager
def receiving() -> Generator[list[object]]:
    """Collect the responses received inside the block, oldest first."""
    received: list[object] = []
    token = _received.set(received)
    try:
        yield received
    finally:
        _received.reset(token)


def _keep(response: object) -> None:
    received = _received.get()
    if received is not None and (not received or received[-1] is not response):
        received.append(response)
