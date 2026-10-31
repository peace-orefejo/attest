"""Load annotators' label files, skipping unfinished ones and setting aside stale ones."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from bench_annotations import (
    ANNOTATOR_PATTERN,
    Annotation,
    AnnotationError,
    Annotations,
    ItemKey,
    label_items,
    run_sha256,
)
from bench_cases import Case


class StaleLabels(BaseModel):
    path: Path
    reason: str


class LoadedLabels(BaseModel):
    annotations: Annotations
    unfinished: list[Path]
    """Label files still holding a blank label, confidence or rationale; they are skipped."""
    stale: list[StaleLabels]
    """Label files for a case that was removed or changed since they were written; skipped.
    Delete them and run `template` again to relabel the current run."""


def load_annotations(root: Path, cases: dict[str, Case]) -> LoadedLabels:
    """Load every annotator's finished, current label files under `root`."""
    if not root.is_dir():
        raise AnnotationError(f"{root}: labels folder not found")
    loaded: Annotations = {}
    unfinished: list[Path] = []
    stale: list[StaleLabels] = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        if not ANNOTATOR_PATTERN.fullmatch(folder.name):
            raise AnnotationError(f"{folder}: annotator folder names are lowercase initials or ids")
        by_case: dict[str, Annotation] = {}
        for path in sorted(folder.glob("*.json")):
            annotation = load_file(path)
            if annotation is None:
                unfinished.append(path)
                continue
            reason = staleness(annotation, cases)
            if reason is not None:
                stale.append(StaleLabels(path=path, reason=reason))
                continue
            by_case[annotation.case_id] = annotation
        loaded[folder.name] = by_case
    return LoadedLabels(annotations=loaded, unfinished=unfinished, stale=stale)


def load_file(path: Path) -> Annotation | None:
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
    return annotation


def staleness(annotation: Annotation, cases: dict[str, Case]) -> str | None:
    """Why these labels no longer describe their case, or None if they still do."""
    case = cases.get(annotation.case_id)
    if case is None:
        return "the case is no longer in the datasets"
    if annotation.check != case.check:
        return f"labelled as {annotation.check!r} but the case is now {case.check!r}"
    if annotation.run_sha256 != run_sha256(case):
        return "the run changed after it was labelled"
    expected_keys = set(label_items(case.expected))
    labelled_keys = set(label_items(annotation.labels))
    if labelled_keys != expected_keys:
        missing = sorted(_describe(key) for key in expected_keys - labelled_keys)
        extra = sorted(_describe(key) for key in labelled_keys - expected_keys)
        return f"the items to label changed (missing: {missing}, extra: {extra})"
    return None


def _unfinished(raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    fields: dict[str, Any] = raw  # pyright: ignore[reportUnknownVariableType]
    if fields.get("confidence") is None or not str(fields.get("rationale") or "").strip():
        return True
    labels = fields.get("labels")
    if isinstance(labels, dict):
        labels = {k: v for k, v in labels.items() if k != "run_label"}  # pyright: ignore[reportUnknownVariableType]
    return _has_blank(labels)


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
