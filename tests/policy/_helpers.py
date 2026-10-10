"""Shared builders for these tests."""

from attest import EvaluationPolicy, EvaluationRule
from attest.trajectory import Step, ToolCall, Trajectory


def _traj(*, answer="Approved.", tools=("check_eligibility",)):
    return Trajectory(
        task="Handle this request.",
        final_answer=answer,
        steps=[Step(tool_call=ToolCall(name=name, output="eligible")) for name in tools],
    )


def _deterministic_policy():
    return EvaluationPolicy(
        name="support",
        version="2.1",
        rules=[
            EvaluationRule(
                id="eligibility-tool", description="Check eligibility first.",
                kind="required_tools", values=["check_eligibility"],
            ),
            EvaluationRule(
                id="no-guarantees", description="Do not guarantee outcomes.",
                kind="forbidden_text", values=["guaranteed"],
            ),
        ],
    )
