"""The reasoning policy in force for the current context, and a record of the levels sent."""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from contextvars import ContextVar

from .reasoning import Reasoning, ReasoningPolicy

_DEFAULT_POLICY = ReasoningPolicy()
_policy: ContextVar[ReasoningPolicy | None] = ContextVar("attest_reasoning", default=None)
_used: ContextVar[dict[str, Reasoning | None] | None] = ContextVar(
    "attest_reasoning_used", default=None
)


@contextlib.contextmanager
def using_reasoning(policy: ReasoningPolicy) -> Generator[None]:
    """Run the enclosed judge calls with this reasoning policy."""
    token = _policy.set(policy)
    try:
        yield
    finally:
        _policy.reset(token)


@contextlib.contextmanager
def recording_reasoning() -> Generator[dict[str, Reasoning | None]]:
    """Collect the level each call site was sent inside the block, as `{site: level}`.

    A site whose client or model takes no reasoning setting is recorded as None. A recording
    inside another one also adds its sites to the outer one.
    """
    outer = _used.get()
    used: dict[str, Reasoning | None] = {}
    token = _used.set(used)
    try:
        yield used
    finally:
        _used.reset(token)
        if outer is not None:
            outer.update(used)


def reasoning_for(site: str | None) -> Reasoning:
    """The level for `site` under the active policy (`"auto"` when none is set).

    A call with no site uses the policy's default.
    """
    policy = _policy.get() or _DEFAULT_POLICY
    return policy.default if site is None else policy.level(site)


def record_sent(site: str | None, level: Reasoning | None) -> None:
    """Note what `site` was sent: its level, or None when no reasoning setting was sent."""
    used = _used.get()
    if site is not None and used is not None:
        used[site] = level
