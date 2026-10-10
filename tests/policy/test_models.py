"""Validation and immutability of policy and rule models."""

import pytest

from attest import Attest, EvaluationPolicy, EvaluationRule

from ._helpers import _deterministic_policy


def test_duplicate_rule_ids_rejected():
    with pytest.raises(ValueError, match="unique"):
        EvaluationPolicy(
            name="bad",
            rules=[
                EvaluationRule(id="same", description="one"),
                EvaluationRule(id="same", description="two"),
            ],
        )


def test_policy_is_deeply_immutable_and_copied_on_input():
    original = _deterministic_policy()
    judge = Attest(policy=original)
    assert judge.policy is not original
    initial_hash = judge.policy.hash
    with pytest.raises(Exception):
        original.name = "changed"
    with pytest.raises(Exception):
        original.rules[0].description = "Always pass"
    with pytest.raises(Exception):
        original.rules += (EvaluationRule(id="extra", description="extra"),)
    assert judge.policy.hash == initial_hash


@pytest.mark.parametrize("value", ["", "   "])
def test_deterministic_rule_rejects_blank_values(value):
    with pytest.raises(ValueError, match="empty or whitespace"):
        EvaluationRule(
            id="bad", description="bad", kind="required_text", values=[value]
        )


def test_names_and_descriptions_reject_whitespace_only():
    with pytest.raises(ValueError):
        EvaluationRule(id="   ", description="valid")
    with pytest.raises(ValueError):
        EvaluationRule(id="valid", description="   ")
    with pytest.raises(ValueError):
        EvaluationPolicy(name="   ", rules=[EvaluationRule(id="x", description="x")])
