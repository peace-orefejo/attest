"""One annotator's labels for benchmark cases, kept apart from the case files so labelling is blind.

Labels live in `<labels>/<annotator>/<case id>.json`, one pretty-printed file per case. The
`trajectory` in each file is a copy for reading and is ignored when the labels are loaded.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator

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
ANNOTATOR_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

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
    trajectory: Trajectory | None = Field(default=None, exclude=True)

    @field_validator("labels", mode="before")
    @classmethod
    def _parse_for_check(cls, value: object, info: ValidationInfo) -> object:
        check = info.data.get("check")
        if not isinstance(check, str) or check not in EXPECTED_MODEL:
            return value
        return EXPECTED_MODEL[check].model_validate(value)


Annotations = dict[str, dict[str, Annotation]]
"""Annotator -> case id -> their annotation."""


class LoadedLabels(BaseModel):
    annotations: Annotations
    unfinished: list[Path]
    """Label files still holding a blank label, confidence or rationale; they are skipped."""


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
        "trajectory": case.trajectory.model_dump(mode="json", exclude_none=True),
    }


def load_annotations(root: Path, cases: dict[str, Case]) -> LoadedLabels:
    """Load every annotator's finished label files under `root`, checking each against its case."""
    if not root.is_dir():
        raise AnnotationError(f"{root}: labels folder not found")
    loaded: Annotations = {}
    unfinished: list[Path] = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        if not ANNOTATOR_PATTERN.match(folder.name):
            raise AnnotationError(f"{folder}: annotator folder names are lowercase initials or ids")
        by_case: dict[str, Annotation] = {}
        for path in sorted(folder.glob("*.json")):
            annotation = load_file(path, cases)
            if annotation is None:
                unfinished.append(path)
            else:
                by_case[annotation.case_id] = annotation
        loaded[folder.name] = by_case
    return LoadedLabels(annotations=loaded, unfinished=unfinished)


def load_file(path: Path, cases: dict[str, Case]) -> Annotation | None:
    """One label file, or None while it still has blanks to fill in."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if _unfinished(raw):
            return None
        annotation = Annotation.model_validate(raw)
    except (ValueError, ValidationError) as exc:
        raise AnnotationError(f"{path}: invalid label file\n{exc}") from exc
    if path.stem != annotation.case_id:
        raise AnnotationError(f"{path}: case_id {annotation.case_id!r} doesn't match the file name")
    case = cases.get(annotation.case_id)
    if case is None:
        raise AnnotationError(f"{path}: no case {annotation.case_id!r} in the datasets")
    if annotation.check != case.check:
        raise AnnotationError(f"{path}: check {annotation.check!r} but the case is {case.check!r}")
    expected_keys = set(label_items(case.expected))
    labelled_keys = set(label_items(annotation.labels))
    if labelled_keys != expected_keys:
        missing = sorted(_describe(key) for key in expected_keys - labelled_keys)
        extra = sorted(_describe(key) for key in labelled_keys - expected_keys)
        raise AnnotationError(
            f"{path}: labels don't match the case's items (missing: {missing}, extra: {extra})"
        )
    return annotation


def _unfinished(raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    fields: dict[str, Any] = raw  # pyright: ignore[reportUnknownVariableType]
    if fields.get("confidence") is None or not str(fields.get("rationale") or "").strip():
        return True
    return _has_blank(fields.get("labels"))


def _has_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, dict):
        return any(_has_blank(v) for v in value.values())  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    if isinstance(value, list):
        return any(_has_blank(v) for v in value)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return False


def _describe(key: ItemKey) -> str:
    return f"{key[0]} {key[1]!r}"
