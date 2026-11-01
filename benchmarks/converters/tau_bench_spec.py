"""The shape of a selected τ-bench run and the helpers its draft labels are written with.

Each step index is the tool call's position in the run (every step is a tool call). Labels
follow `benchmarks/annotations/guidelines.md` and were written by reading the run, not from
attest's output or from τ-bench's reward.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

RETAIL = "gpt-4o-retail.json"
AIRLINE = "gpt-4o-airline.json"


class CaseSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    check: str
    category: str
    upstream_file: str
    upstream_index: int
    task_id: int
    trial: int
    later_user_turns: tuple[int, ...] = ()
    expected: dict[str, object]
    notes: str


def tool_calls(errors: dict[int, str], count: int) -> list[dict[str, object]]:
    return [{"step": step, "verdict": errors.get(step, "correct")} for step in range(count)]


def recovery_calls(errors: dict[int, tuple[str, str]], count: int) -> list[dict[str, object]]:
    labels = [errors.get(step, ("correct", "none")) for step in range(count)]
    return [
        {"step": step, "verdict": verdict, "recovery": recovery}
        for step, (verdict, recovery) in enumerate(labels)
    ]


def claims(*pairs: tuple[str, str]) -> list[dict[str, object]]:
    return [{"text": text, "label": label} for text, label in pairs]


FOLD = (
    "the task is the first user message plus the listed later user turns that add or change "
    "requirements; identity details, confirmations of an already stated request, pleasantries "
    "and the simulator's ###STOP### token are left out, and the agent's intermediate messages "
    "to the user are dropped (text sent alongside a tool call is kept as that step's thought)."
)
