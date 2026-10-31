from attest.utils.failures import MAX_DETAIL_CHARS, failure_reason


def test_names_the_error_type_and_message():
    reason = failure_reason("The role judge", TimeoutError("timed\n  out"))
    assert reason == "The role judge failed (TimeoutError: timed out)."


def test_clips_a_long_message():
    reason = failure_reason("A call", RuntimeError("x" * 5_000))
    assert len(reason) < MAX_DETAIL_CHARS + 50
    assert reason.endswith("...).")


def test_an_empty_message_shows_only_the_type():
    assert failure_reason("A call", KeyError()) == "A call failed (KeyError)."
