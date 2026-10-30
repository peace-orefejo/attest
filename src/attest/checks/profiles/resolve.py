from __future__ import annotations

from pydantic import BaseModel, Field

from ...trajectory import Trajectory
from ...utils.json_types import JsonObject
from .detect import detect_answer_kind
from .registry import AUTO


class ResolvedKind(BaseModel):
    """The concrete answer kind to grade with and the report metadata to record."""

    kind: str
    metadata: JsonObject = Field(default_factory=dict)


def resolve_answer_kind(traj: Trajectory, answer_kind: str) -> ResolvedKind:
    """Resolve "auto" to a concrete kind; hint when explicit "factual" meets code evidence."""
    if answer_kind == AUTO:
        detection = detect_answer_kind(traj)
        return ResolvedKind(
            kind=detection.kind,
            metadata={"answer_kind": detection.kind, "answer_kind_reason": detection.reason},
        )
    if answer_kind == "factual" and detect_answer_kind(traj).kind == "code":
        return ResolvedKind(kind=answer_kind, metadata={"answer_kind_hint": "code"})
    return ResolvedKind(kind=answer_kind)
