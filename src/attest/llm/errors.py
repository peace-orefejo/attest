"""Classify provider failures: hard API errors surface, empty or unparseable output retries."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Literal, cast

from pydantic import ValidationError

from .stop_reasons import stopped_at_limit

_INSTRUCTOR_TRUNCATED = "IncompleteOutputException"
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


class TruncatedOutput(RuntimeError):
    """The model stopped at `max_tokens` before it finished the structured answer.

    Often the model spent its output budget reasoning. It is not retried, since the same
    request would stop in the same place; checks report the call as `unchecked`.
    `completion` is the provider's response when there is one: its tokens were billed, and
    they count in `Usage` and against a `Budget`.
    """

    def __init__(self, message: str, *, completion: object | None = None) -> None:
        super().__init__(message)
        self.completion = completion


class UnreadableOutput(RuntimeError):
    """The model finished, but its answer isn't the structured output asked for.

    Retried like an empty answer when the text failed validation. `completion` is the billed
    response.
    """

    def __init__(self, message: str, *, completion: object | None = None) -> None:
        super().__init__(message)
        self.completion = completion


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


def is_truncated(err: Exception) -> bool:
    """The output was cut off at the token limit: `TruncatedOutput`, instructor's equivalent, or
    a failed attempt whose response stopped at the limit (Gemini's `MAX_TOKENS`)."""
    if any(
        isinstance(cause, TruncatedOutput) or type(cause).__name__ == _INSTRUCTOR_TRUNCATED
        for cause in _cause_chain(err)
    ):
        return True
    billed = failed_completions(err)
    return bool(billed) and stopped_at_limit(billed[-1])


def failed_completions(err: BaseException) -> list[object]:
    """The provider responses a failed call was billed for, oldest first, so usage counts them.

    Read from attest's own errors, or from instructor's failed attempts or last completion.
    """
    for cause in _cause_chain(err):
        if isinstance(cause, TruncatedOutput | UnreadableOutput):
            return [] if cause.completion is None else [cause.completion]
        attempts = _attempt_completions(getattr(cause, "failed_attempts", None))
        if attempts:
            return attempts
        last = getattr(cause, "last_completion", None)
        if last is not None:
            return [last]
    return []


def _attempt_completions(attempts: object) -> list[object]:
    if not isinstance(attempts, Sequence) or isinstance(attempts, str):
        return []
    found = (getattr(attempt, "completion", None) for attempt in cast("Sequence[object]", attempts))
    return [completion for completion in found if completion is not None]


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
