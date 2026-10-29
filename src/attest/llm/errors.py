"""Classify provider failures: hard API errors surface, empty or unparseable output retries."""

from __future__ import annotations

from collections.abc import Iterator

from pydantic import ValidationError

_EMPTY_MARKERS = ("has no attribute 'parts'", "'NoneType' object is not iterable")


def api_error(err: Exception) -> BaseException | None:
    """The provider's HTTP error (auth, billing, bad request...) anywhere in the cause chain."""
    return next((e for e in _cause_chain(err) if _http_status(e) is not None), None)


def is_empty_response(err: Exception) -> bool:
    """An empty/blocked candidate or unparseable output: transient, so worth another attempt."""
    for cause in _cause_chain(err):
        if isinstance(cause, ValidationError):
            return True
        if any(marker in str(cause) for marker in _EMPTY_MARKERS):
            return True
    return False


def _cause_chain(err: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = err
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _http_status(err: BaseException) -> int | None:
    status = getattr(err, "status_code", None)
    if isinstance(status, int):
        return status
    code = getattr(err, "code", None)
    if isinstance(code, int) and hasattr(err, "details"):
        return code
    return None
