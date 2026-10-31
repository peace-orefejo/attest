"""Write blank label files for one annotator, flagging existing ones that no longer fit."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from bench_annotations import AnnotationError, blank_labels, run_sha256, template
from bench_cases import Case
from bench_label_files import StaleLabels

LABEL_FIELDS = frozenset({"label", "verdict", "recovery"})


class Templates(BaseModel):
    written: int
    kept: int
    stale: list[StaleLabels]
    """Existing files written for an older run or older items; delete them and run again."""


def write_templates(
    folder: Path, cases: list[Case], *, forbidden: Callable[[Path], bool] | None = None
) -> Templates:
    """Write a blank label file per case into `folder`, keeping files already there.

    `forbidden` says where a file may not land (after following symlinks); writing there raises
    AnnotationError before anything is written to it.
    """
    _guard(folder, forbidden)
    folder.mkdir(parents=True, exist_ok=True)
    _guard(folder, forbidden)
    written = kept = 0
    stale: list[StaleLabels] = []
    for case in cases:
        path = folder / f"{case.id}.json"
        if path.exists():
            kept += 1
            reason = template_staleness(path, case)
            if reason is not None:
                stale.append(StaleLabels(path=path, reason=reason))
            continue
        _guard(path, forbidden)
        path.write_text(json.dumps(template(case), indent=2) + "\n", encoding="utf-8")
        written += 1
    return Templates(written=written, kept=kept, stale=stale)


def template_staleness(path: Path, case: Case) -> str | None:
    """Why an existing label file, finished or not, no longer fits `case`; None if it does."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return "it isn't valid JSON"
    if not isinstance(raw, dict):
        return "it isn't a label file"
    fields: dict[str, Any] = raw  # pyright: ignore[reportUnknownVariableType]
    if fields.get("run_sha256") != run_sha256(case):
        return "it is for an older version of its run"
    if _shape(fields.get("labels")) != _shape(blank_labels(case)):
        return "the items to label changed"
    return None


def _shape(value: object) -> object:
    """`value` with every label blanked and list order ignored, so only the items are compared."""
    if isinstance(value, dict):
        items: dict[str, Any] = value  # pyright: ignore[reportUnknownVariableType]
        return {
            key: None if key in LABEL_FIELDS else _shape(item)
            for key, item in items.items()
            if key != "run_label"
        }
    if isinstance(value, list):
        entries: list[Any] = value  # pyright: ignore[reportUnknownVariableType]
        return sorted((_shape(entry) for entry in entries), key=json.dumps)
    return value


def _guard(path: Path, forbidden: Callable[[Path], bool] | None) -> None:
    if forbidden is not None and forbidden(path):
        raise AnnotationError(
            f"{path} resolves to {path.resolve()}, inside this repository; the dataset is "
            f"private, so keep its labels out of it"
        )
