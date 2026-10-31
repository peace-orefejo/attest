"""One annotator's labels for benchmark cases, kept apart from the case files so labelling is blind.

Labels live in `<labels>/<annotator>/<case id>.json`, one pretty-printed file per case. The
`trajectory` in each file is a copy for reading; `run_sha256` ties the labels to that exact run,
so labels given before a run was edited are never confirmed for the edited run.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from attest import Trajectory
from bench_cases import (
    EXPECTED_MODEL,
    Case,
    CheckName,
    Expected,
    FaithfulnessExpected,
    InjectionExpected,
    RecoveryExpected,
    RoleExpected,
    ToolUseExpected,
)

LABELS_DIR = Path(__file__).resolve().parent.parent / "annotations" / "labels"
ANNOTATOR_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*")
"""Annotator names: lowercase initials or ids. Match with `fullmatch`."""

Confidence = Literal["high", "medium", "low"]
Dimension = Literal["claim", "verdict", "recovery", "label"]
ItemKey = tuple[Dimension, str]
"""One labelled item: what kind of label it is, and what it is about (a claim, `step N`, `run`)."""


class AnnotationError(ValueError):
    """A label file is malformed or doesn't match its case."""


class Annotation(BaseModel):
    """One annotator's labels for one case, with how sure they are and why."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    check: CheckName
    labels: Expected
    confidence: Confidence
    ambiguous: bool = False
    rationale: str = Field(min_length=1)
    run_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    trajectory: Trajectory | None = Field(default=None, exclude=True)

    @field_validator("labels", mode="before")
    @classmethod
    def _parse_for_check(cls, value: object, info: ValidationInfo) -> object:
        check = info.data.get("check")
        if not isinstance(check, str) or check not in EXPECTED_MODEL:
            return value
        return EXPECTED_MODEL[check].model_validate(value)

    @model_validator(mode="after")
    def _no_run_label(self) -> Annotation:
        if isinstance(self.labels, FaithfulnessExpected) and "run_label" in (
            self.labels.model_fields_set
        ):
            raise ValueError("leave run_label out: merge derives it from the claim labels")
        return self


Annotations = dict[str, dict[str, Annotation]]
"""Annotator -> case id -> their annotation."""


def run_sha256(case: Case) -> str:
    """Fingerprint of the run an annotator reads, so labels can't outlive an edit to it."""
    return hashlib.sha256(case.trajectory.model_dump_json().encode()).hexdigest()


def label_items(expected: Expected) -> dict[ItemKey, str]:
    """Every label in `expected`, keyed so two annotators' labels can be lined up."""
    if isinstance(expected, FaithfulnessExpected):
        return {("claim", claim.text): claim.label for claim in expected.claims}
    if isinstance(expected, RecoveryExpected):
        items: dict[ItemKey, str] = {}
        for call in expected.calls:
            items[("verdict", f"step {call.step}")] = call.verdict
            items[("recovery", f"step {call.step}")] = call.recovery
        return items
    if isinstance(expected, ToolUseExpected):
        return {("verdict", f"step {call.step}"): call.verdict for call in expected.calls}
    assert isinstance(expected, InjectionExpected | RoleExpected)
    return {("label", "run"): expected.label}


def blank_labels(case: Case) -> dict[str, Any]:
    """The `labels` skeleton for a case, with every label left null for the annotator."""
    expected = case.expected
    if isinstance(expected, FaithfulnessExpected):
        return {"claims": [{"text": claim.text, "label": None} for claim in expected.claims]}
    if isinstance(expected, RecoveryExpected):
        return {
            "calls": [
                {"step": call.step, "verdict": None, "recovery": None} for call in expected.calls
            ]
        }
    if isinstance(expected, ToolUseExpected):
        return {"calls": [{"step": call.step, "verdict": None} for call in expected.calls]}
    return {"label": None}


def template(case: Case) -> dict[str, Any]:
    """A label file to fill in: the run to read, and labels left blank. No existing labels."""
    return {
        "case_id": case.id,
        "check": case.check,
        "labels": blank_labels(case),
        "confidence": None,
        "ambiguous": False,
        "rationale": "",
        "run_sha256": run_sha256(case),
        "trajectory": case.trajectory.model_dump(mode="json", exclude_none=True),
    }
