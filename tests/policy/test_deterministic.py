"""Rules decided without an LLM."""

from attest import Attest, EvaluationPolicy, EvaluationRule

from ._helpers import _traj


def test_required_tool_order_is_a_subsequence():
    policy = EvaluationPolicy(
        name="refund",
        rules=[EvaluationRule(
            id="order", description="Check before issuing.", kind="required_tool_order",
            values=["check_eligibility", "issue_refund"],
        )],
    )
    assert Attest(policy=policy).policy_check(
        _traj(tools=("check_eligibility", "audit", "issue_refund"))
    ).passed is True
    assert Attest(policy=policy).policy_check(
        _traj(tools=("issue_refund", "check_eligibility"))
    ).passed is False
