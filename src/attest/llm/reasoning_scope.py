"""The reasoning policy in force for the current context, and a record of the levels used."""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from contextvars import ContextVar

from .reasoning import Reasoning, ReasoningPolicy

_DEFAULT_POLICY = ReasoningPolicy()
_policy: ContextVar[ReasoningPolicy | None] = ContextVar("attest_reasoning", default=None)
_used: ContextVar[dict[str, Reasoning] | None] = ContextVar("attest_reasoning_used", default=None)


@contextlib.contextmanager
def using_reasoning(policy: ReasoningPolicy) -> Generator[None]:
    """Run the enclosed judge calls with this reasoning policy."""
    token = _policy.set(policy)
    try:
        yield
    finally:
        _policy.reset(token)


@contextlib.contextmanager
def recording_reasoning() -> Generator[dict[str, Reasoning]]:
    """Collect the level each call site used inside the block, as `{site: level}`."""
    used: dict[str, Reasoning] = {}
    token = _used.set(used)
    try:
        yield used
    finally:
        _used.reset(token)


def reasoning_for(site: str | None) -> Reasoning:
    """The level for `site` under the active policy (`"auto"` when none is set), recorded.

    A call with no site uses the policy's default and isn't recorded.
    """
    policy = _policy.get() or _DEFAULT_POLICY
    if site is None:
        return policy.default
    level = policy.level(site)
    used = _used.get()
    if used is not None:
        used[site] = level
    return level
