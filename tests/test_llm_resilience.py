"""call() retries transient empty/blocked provider responses, then fails clearly."""

import pytest

import attest._llm as llm
from attest.checks.verify import VerdictOut

_EMPTY = AttributeError("'NoneType' object has no attribute 'parts'")


class _FlakyClient:
    def __init__(self, fails, exc):
        self.fails = fails
        self.exc = exc
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fails:
            raise self.exc
        return VerdictOut(verdict="supported")


def test_retries_transient_empty_then_succeeds():
    client = _FlakyClient(fails=2, exc=_EMPTY)
    out = llm.call(system="s", user="u", output=VerdictOut, client=client)
    assert out.verdict == "supported"
    assert client.calls == 3


def test_raises_clear_error_when_always_empty():
    client = _FlakyClient(fails=99, exc=_EMPTY)
    with pytest.raises(RuntimeError, match="no parseable content"):
        llm.call(system="s", user="u", output=VerdictOut, client=client, attempts=2)


def test_propagates_non_empty_error_immediately():
    client = _FlakyClient(fails=99, exc=ValueError("bad schema"))
    with pytest.raises(ValueError):
        llm.call(system="s", user="u", output=VerdictOut, client=client)
    assert client.calls == 1


class _CapturingClient:
    def __init__(self):
        self.system = None

    def create(self, **kwargs):
        self.system = kwargs["messages"][0]["content"]
        return VerdictOut(verdict="supported")


def test_guard_is_prepended_to_every_call():
    client = _CapturingClient()
    llm.call(system="You are a fact-checker.", user="u", output=VerdictOut, client=client)
    assert "UNTRUSTED DATA" in client.system
    assert "MUST NOT follow" in client.system
    assert "You are a fact-checker." in client.system  # the check's own prompt still there


class _BillingError(Exception):
    status_code = 400


class _GoogleError(Exception):
    code = 403
    details = {"error": "PERMISSION_DENIED"}


def _wrapped(inner):
    try:
        raise inner
    except Exception as cause:
        try:
            raise RuntimeError("InstructorRetryException: Max retries exceeded") from cause
        except RuntimeError as outer:
            return outer


def test_hard_api_error_inside_retry_wrapper_is_not_retried():
    client = _FlakyClient(fails=99, exc=_wrapped(_BillingError("credit balance is too low")))
    with pytest.raises(_BillingError, match="credit balance"):
        llm.call(system="s", user="u", output=VerdictOut, client=client)
    assert client.calls == 1


def test_google_api_error_is_not_retried():
    client = _FlakyClient(fails=99, exc=_wrapped(_GoogleError("403 PERMISSION_DENIED")))
    with pytest.raises(_GoogleError):
        llm.call(system="s", user="u", output=VerdictOut, client=client)
    assert client.calls == 1


def test_bare_api_error_propagates_unchanged():
    client = _FlakyClient(fails=99, exc=_BillingError("bad request"))
    with pytest.raises(_BillingError):
        llm.call(system="s", user="u", output=VerdictOut, client=client)
    assert client.calls == 1


def test_wrapped_validation_failure_is_still_retried():
    from pydantic import ValidationError

    try:
        VerdictOut.model_validate({"verdict": "nope"})
    except ValidationError as ve:
        client = _FlakyClient(fails=1, exc=_wrapped(ve))
    out = llm.call(system="s", user="u", output=VerdictOut, client=client)
    assert out.verdict == "supported"
    assert client.calls == 2


def test_gemini_empty_candidate_is_retried():
    client = _FlakyClient(fails=1, exc=_wrapped(TypeError("'NoneType' object is not iterable")))
    llm.call(system="s", user="u", output=VerdictOut, client=client)
    assert client.calls == 2
