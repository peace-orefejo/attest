"""Classify provider failures: hard API errors surface, empty or unparseable output retries."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Literal

from pydantic import ValidationError

_EMPTY_MARKERS = ("has no attribute 'parts'", "'NoneType' object is not iterable")

ConfigProblem = Literal["authentication", "permission", "model_not_found"]

_CONFIG_STATUS: dict[int, ConfigProblem] = {
    401: "authentication",
    403: "permission",
    404: "model_not_found",
}
_CONFIG_MESSAGE: dict[ConfigProblem, str] = {
    "authentication": "The provider rejected the API key (HTTP 401). Check this provider's key.",
    "permission": "The API key isn't allowed to use this model or endpoint (HTTP 403).",
    "model_not_found": "The provider doesn't recognise this model (HTTP 404). Check the model id.",
}


class ProviderConfigError(RuntimeError):
    """The grading model can't be used at all: a bad key, missing permission or unknown model.

    This is a setup mistake, not an inconclusive evaluation, so checks never turn it into an
    `unchecked` finding: it stops the evaluation. The message never includes the key or the
    provider's response body.
    """

    def __init__(self, problem: ConfigProblem, status: int) -> None:
        super().__init__(_CONFIG_MESSAGE[problem])
        self.problem: ConfigProblem = problem
        self.status = status


def config_error(err: Exception) -> ProviderConfigError | None:
    """A `ProviderConfigError` when the provider refused the key, permission or model."""
    hard = api_error(err)
    status = _http_status(hard) if hard is not None else None
    problem = _CONFIG_STATUS.get(status) if status is not None else None
    return ProviderConfigError(problem, status) if problem is not None and status else None


def is_transient(err: Exception) -> bool:
    """A rate limit, timeout or server error the provider may not repeat on another attempt."""
    hard = api_error(err)
    status = _http_status(hard) if hard is not None else None
    return status is not None and (status in (408, 409, 429) or status >= 500)


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
