"""The naive LLM-as-judge baseline: reads the full trajectory and grades the answer."""

from __future__ import annotations

from pydantic import BaseModel

from ..llm import call
from ..prompts.judge import JUDGE_SYSTEM, judge_user
from ..trajectory import Trajectory


class JudgeVerdict(BaseModel):
    """Whether the agent's final answer is good, with a reason."""

    passed: bool
    reason: str = ""


def naive_judge(traj: Trajectory) -> JudgeVerdict:
    return call(system=JUDGE_SYSTEM, user=judge_user(traj), output=JudgeVerdict)
