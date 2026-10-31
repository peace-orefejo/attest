"""Describe a failed judge call in a finding's reason, short enough to read."""

from __future__ import annotations

MAX_DETAIL_CHARS = 300


def failure_reason(what: str, error: BaseException) -> str:
    """`what` failed, with the error's type and a clipped message."""
    detail = " ".join(str(error).split())
    if len(detail) > MAX_DETAIL_CHARS:
        detail = detail[:MAX_DETAIL_CHARS] + "..."
    name = type(error).__name__
    return f"{what} failed ({name}: {detail})." if detail else f"{what} failed ({name})."
