"""The benchmark case format: one labelled run per JSONL line, with check-specific labels."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from attest import Trajectory

CheckName = Literal["faithfulness", "tool_use", "recovery", "prompt_injection", "role_adherence"]
CHECKS: tuple[CheckName, ...] = (
    "faithfulness",
    "tool_use",
    "recovery",
    "prompt_injection",
    "role_adherence",
)
Split = Literal["dev", "heldout"]
SPLITS: tuple[Split, ...] = ("dev", "heldout")

ClaimLabel = Literal["supported", "unsupported", "unverifiable"]
RunLabel = Literal["pass", "review", "block"]
ToolVerdictLabel = Literal[
    "correct", "disallowed_tool", "error_silent", "error_claimed_success", "incorrect"
]
RecoveryLabel = Literal["none", "retried", "fallback", "acknowledged", "silent", "claimed_success"]
InjectionLabel = Literal["none", "payload", "compromised"]
RoleLabel = Literal["in_scope", "appropriately_refused", "out_of_scope_complied"]

LABELS: dict[CheckName, tuple[str, ...]] = {
    "faithfulness": ("supported", "unsupported", "unverifiable"),
    "tool_use": (
        "correct",
        "disallowed_tool",
        "error_silent",
        "error_claimed_success",
        "incorrect",
    ),
    "recovery": ("none", "retried", "fallback", "acknowledged", "silent", "claimed_success"),
    "prompt_injection": ("none", "payload", "compromised"),
    "role_adherence": ("in_scope", "appropriately_refused", "out_of_scope_complied"),
}
"""Every label a person may give, per check, in display order."""


class BinaryView(BaseModel):
    """A two-class reading of one check's labels: `negative` labels are the clean side and
    every other label is positive. A prediction of `missing`, `error` or `not_run` is never a
    detection."""

    model_config = ConfigDict(frozen=True)

    name: str
    negative: frozenset[str]
    question: str

    def positive(self, labels: tuple[str, ...]) -> list[str]:
        return [label for label in labels if label not in self.negative]


def _violation(negative: set[str], question: str) -> BinaryView:
    return BinaryView(name="violation_detection", negative=frozenset(negative), question=question)


BINARY_VIEWS: dict[CheckName, tuple[BinaryView, ...]] = {
    "faithfulness": (
        BinaryView(
            name="contradiction_detection",
            negative=frozenset({"supported", "unverifiable"}),
            question="Does attest flag claims the evidence contradicts (unsupported)?",
        ),
        BinaryView(
            name="evidence_sufficiency",
            negative=frozenset({"supported"}),
            question="Does attest flag claims the evidence doesn't back "
            "(unsupported or unverifiable)?",
        ),
    ),
    "tool_use": (_violation({"correct"}, "Does attest flag a tool call that went wrong?"),),
    "recovery": (
        _violation(
            {"none", "retried", "fallback", "acknowledged"},
            "Does attest flag a failed call that was neither recovered nor reported?",
        ),
    ),
    "prompt_injection": (
        _violation({"none"}, "Does attest flag a run with an injection attempt?"),
    ),
    "role_adherence": (
        _violation(
            {"in_scope", "appropriately_refused"},
            "Does attest flag a run where the agent did out-of-scope work?",
        ),
    ),
}
"""The binary views reported per check. Faithfulness has two, because `unverifiable` (nothing
backs the claim) is not a contradiction; every other check has one violation view."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LabelledClaim(_Strict):
    text: str = Field(min_length=1)
    label: ClaimLabel


class FaithfulnessExpected(_Strict):
    claims: list[LabelledClaim] = Field(min_length=1)
    run_label: RunLabel | None = None


class LabelledCall(_Strict):
    step: int = Field(ge=0)
    verdict: ToolVerdictLabel


class LabelledRecoveryCall(LabelledCall):
    recovery: RecoveryLabel


class ToolUseExpected(_Strict):
    calls: list[LabelledCall] = Field(min_length=1)


class RecoveryExpected(_Strict):
    calls: list[LabelledRecoveryCall] = Field(min_length=1)


class InjectionExpected(_Strict):
    label: InjectionLabel


class RoleExpected(_Strict):
    label: RoleLabel


Expected = (
    FaithfulnessExpected | ToolUseExpected | RecoveryExpected | InjectionExpected | RoleExpected
)
EXPECTED_MODEL: dict[str, type[Expected]] = {
    "faithfulness": FaithfulnessExpected,
    "tool_use": ToolUseExpected,
    "recovery": RecoveryExpected,
    "prompt_injection": InjectionExpected,
    "role_adherence": RoleExpected,
}


class Case(_Strict):
    """One labelled run. Labels come from people, never from attest's output."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    check: CheckName
    category: str = Field(pattern=r"^[a-z0-9_]+$")
    source: Literal["synthetic", "real", "community"]
    label_status: Literal["draft", "confirmed"]
    annotators: list[str] = Field(default_factory=list[str])
    trajectory: Trajectory
    expected: Expected
    notes: str = ""

    @field_validator("expected", mode="before")
    @classmethod
    def _parse_for_check(cls, value: object, info: ValidationInfo) -> object:
        check = info.data.get("check")
        if not isinstance(check, str) or check not in EXPECTED_MODEL:
            return value
        return EXPECTED_MODEL[check].model_validate(value)

    @model_validator(mode="after")
    def _consistent(self) -> Case:
        if type(self.expected) is not EXPECTED_MODEL[self.check]:
            raise ValueError(f"expected does not match check {self.check!r}")
        if self.label_status == "confirmed" and len(set(self.annotators)) < 2:
            raise ValueError("a confirmed case needs at least two distinct annotators")
        if isinstance(self.expected, FaithfulnessExpected):
            texts = [claim.text for claim in self.expected.claims]
            if len(set(texts)) != len(texts):
                raise ValueError("claim texts must be unique within a case")
        if isinstance(self.expected, ToolUseExpected | RecoveryExpected):
            self._check_call_steps([call.step for call in self.expected.calls])
        return self

    def _check_call_steps(self, labelled: list[int]) -> None:
        actual = [indexed.step for indexed in self.trajectory.tool_calls()]
        if sorted(labelled) != actual:
            raise ValueError(
                f"expected.calls must label every tool call exactly once: "
                f"labelled steps {sorted(labelled)}, tool-call steps {actual}"
            )
