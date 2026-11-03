"""The reasoning levels, the per-check policy and the room each call gets to reason."""

import pytest

from attest.llm.reasoning import (
    CALL_SITES,
    MAX_REQUEST_TOKENS,
    REASONING_ALLOWANCE,
    ReasoningPolicy,
    answer_room,
    describe_reasoning,
    parse_reasoning,
    reasoning_policy,
)
from attest.llm.reasoning_scope import (
    reasoning_for,
    record_sent,
    recording_reasoning,
    using_reasoning,
)


def test_the_default_is_auto_everywhere():
    policy = ReasoningPolicy()
    assert {policy.level(site) for site in CALL_SITES} == {"auto"}


def test_a_single_level_applies_to_every_call_site():
    policy = reasoning_policy("high")
    assert {policy.level(site) for site in CALL_SITES} == {"high"}


def test_the_most_specific_key_wins():
    policy = reasoning_policy(
        {"faithfulness": "medium", "faithfulness.extract": "off", "default": "low"}
    )
    assert policy.level("faithfulness.extract") == "off"
    assert policy.level("faithfulness.verify") == "medium"
    assert policy.level("role") == "low"


def test_a_policy_passes_through_unchanged():
    policy = ReasoningPolicy(default="off")
    assert reasoning_policy(policy) is policy


@pytest.mark.parametrize(
    "value",
    ["maximum", {"faithfulnes": "low"}, {"role": "extreme"}, {"default": "xhigh"}],
)
def test_an_unknown_level_or_key_is_a_value_error(value):
    with pytest.raises(ValueError):
        reasoning_policy(value)


def test_parse_reads_one_level_or_pairs():
    assert parse_reasoning("medium") == ReasoningPolicy(default="medium")
    parsed = parse_reasoning(" faithfulness=medium , default=off ")
    assert parsed == ReasoningPolicy(default="off", checks={"faithfulness": "medium"})


@pytest.mark.parametrize("text", ["faithfulness", "role=high,oops", "loud", "made_up=low"])
def test_parse_rejects_bad_text(text):
    with pytest.raises(ValueError):
        parse_reasoning(text)


def test_describe_round_trips_through_parse():
    for policy in (ReasoningPolicy(), ReasoningPolicy(default="off", checks={"role": "high"})):
        assert parse_reasoning(describe_reasoning(policy)) == policy
    assert describe_reasoning(ReasoningPolicy()) == "auto"


def test_answer_room_adds_the_allowance_for_the_level():
    assert answer_room(300, "off") == 300
    assert answer_room(300, "auto") == 300 + REASONING_ALLOWANCE["auto"]
    assert answer_room(512, "high") == 512 + REASONING_ALLOWANCE["high"]


def test_answer_room_stays_under_the_request_cap_but_never_below_the_answer():
    assert answer_room(8192, "high") == MAX_REQUEST_TOKENS
    assert answer_room(MAX_REQUEST_TOKENS + 5, "high") == MAX_REQUEST_TOKENS + 5


def test_small_caps_can_no_longer_starve_the_answer():
    for level in ("auto", "low", "medium", "high"):
        assert answer_room(300, level) >= 300 + 4096


def test_the_scope_sets_the_level_of_each_site():
    with using_reasoning(reasoning_policy({"role": "high"})):
        assert reasoning_for("role") == "high"
        assert reasoning_for("faithfulness.verify") == "auto"
        assert reasoning_for(None) == "auto"


def test_a_recording_keeps_what_was_sent_and_adds_to_an_outer_one():
    with recording_reasoning() as outer:
        record_sent("writer", "auto")
        with recording_reasoning() as inner:
            record_sent("role", None)
            record_sent(None, "high")
        assert inner == {"role": None}
    assert outer == {"writer": "auto", "role": None}


@pytest.mark.parametrize(
    ("text", "described"),
    [
        ("auto", "auto"),
        ("default=auto,role=auto", "auto"),
        ("default=off,faithfulness=off,faithfulness.verify=off", "off"),
        ("faithfulness=high,faithfulness.verify=high", "default=auto,faithfulness=high"),
        (
            "faithfulness=high,faithfulness.verify=auto",
            "default=auto,faithfulness=high,faithfulness.verify=auto",
        ),
        ("role=high,default=off", "default=off,role=high"),
    ],
)
def test_equivalent_policies_are_described_the_same(text, described):
    assert describe_reasoning(parse_reasoning(text)) == described


def test_without_a_scope_calls_use_auto():
    assert reasoning_for("writer") == "auto"
