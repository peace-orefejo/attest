"""One annotator's own label files, as the labelling page reads and writes them.

Only `<labels>/<annotator>/` is ever opened. A case id is accepted only if it names a `.json`
file already in that folder, so no path is ever built from what a request sends. Runs are read
from the label files' own `trajectory` copy; the case files are used only to tell whether a
label file is stale, and nothing from them (draft labels, notes, category) is sent to the page.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from bench_annotations import AnnotationError
from bench_cases import Case, CheckName, Split
from bench_label_files import load_file, staleness
from bench_template import Templates, template_staleness, write_templates
from label_ui_files import label_values, started, write_atomic
from label_ui_validate import check_submission

Status = Literal["blank", "partial", "done", "stale", "invalid"]


class CaseSummary(BaseModel):
    id: str
    check: str
    split: str | None
    status: Status
    ambiguous: bool
    labelled: int
    total: int
    reason: str | None = None
    """Why a stale or invalid file can't be edited here."""


class CaseFile(BaseModel):
    """What the page needs to label one case: the run and this annotator's labels, no more."""

    summary: CaseSummary
    labels: Any
    confidence: str | None
    ambiguous: bool
    rationale: str
    trajectory: Any
    version: str
    """A fingerprint of the file as read, so a save can't overwrite a newer edit."""


class SaveResult(BaseModel):
    saved: bool
    errors: list[str] = []
    case: CaseFile | None = None


class LabelStore:
    def __init__(
        self,
        folder: Path,
        cases: dict[str, Case],
        splits: dict[str, Split],
        forbidden: Callable[[Path], bool] | None = None,
    ) -> None:
        self.folder = folder
        self._cases = cases
        self._splits = splits
        self._forbidden = forbidden
        self._lock = threading.Lock()

    def files(self) -> dict[str, Path]:
        """Case id -> label file, for the `.json` files directly in this annotator's folder."""
        if not self.folder.is_dir():
            return {}
        root = self.folder.resolve()
        return {
            path.stem: path
            for path in sorted(self.folder.glob("*.json"))
            if path.is_file() and path.resolve().parent == root and not path.name.startswith(".")
        }

    def summaries(self) -> list[CaseSummary]:
        return [self._read(case_id, path)[0] for case_id, path in self.files().items()]

    def case(self, case_id: str) -> CaseFile | None:
        path = self.files().get(case_id)
        if path is None:
            return None
        summary, raw, version = self._read(case_id, path)
        return CaseFile(
            summary=summary,
            labels=raw.get("labels"),
            confidence=raw.get("confidence"),
            ambiguous=bool(raw.get("ambiguous")),
            rationale=str(raw.get("rationale") or ""),
            trajectory=raw.get("trajectory"),
            version=version,
        )

    def save(self, case_id: str, submitted: object, version: object) -> SaveResult | None:
        path = self.files().get(case_id)
        if path is None:
            return None
        with self._lock:
            summary, raw, current = self._read(case_id, path)
            if summary.status in ("stale", "invalid"):
                return SaveResult(saved=False, errors=[f"read-only: {summary.reason}"])
            if version != current:
                return SaveResult(
                    saved=False, errors=["the file changed on disk since you opened it; reload"]
                )
            checked = check_submission(raw, submitted)
            if checked.data is None:
                return SaveResult(saved=False, errors=checked.errors)
            if self._forbidden is not None and self._forbidden(path):
                raise AnnotationError(
                    f"{path} resolves inside this repository; the data is private"
                )
            write_atomic(path, checked.data)
        return SaveResult(saved=True, case=self.case(case_id))

    def create(self, checks: list[CheckName], splits: list[Split]) -> Templates:
        """Write blank label files with the `template` command's own logic."""
        chosen = [
            case
            for case in self._cases.values()
            if case.check in checks and self._splits.get(case.id) in splits
        ]
        with self._lock:
            return write_templates(self.folder, chosen, forbidden=self._forbidden)

    def _read(self, case_id: str, path: Path) -> tuple[CaseSummary, dict[str, Any], str]:
        content = path.read_bytes()
        version = hashlib.sha256(content).hexdigest()
        try:
            raw = json.loads(content)
        except ValueError:
            raw = None
        if not isinstance(raw, dict):
            return self._summary(case_id, {}, "invalid", "it isn't a label file"), {}, version
        fields: dict[str, Any] = raw  # pyright: ignore[reportUnknownVariableType]
        status, reason = self._status(case_id, path, fields)
        return self._summary(case_id, fields, status, reason), fields, version

    def _status(self, case_id: str, path: Path, raw: dict[str, Any]) -> tuple[Status, str | None]:
        if raw.get("case_id") != case_id:
            return "invalid", "its case_id doesn't match the file name"
        case = self._cases.get(case_id)
        if case is None:
            return "stale", "the case is no longer in the datasets"
        if raw.get("check") != case.check:
            return "stale", f"labelled as {raw.get('check')!r} but the case is now {case.check!r}"
        reason = template_staleness(path, case)
        if reason is not None:
            return "stale", reason
        try:
            annotation = load_file(path)
        except AnnotationError as exc:
            return "invalid", str(exc).splitlines()[-1]
        if annotation is not None:
            reason = staleness(annotation, self._cases)
            return ("stale", reason) if reason is not None else ("done", None)
        return ("partial" if started(raw) else "blank"), None

    def _summary(
        self, case_id: str, raw: dict[str, Any], status: Status, reason: str | None
    ) -> CaseSummary:
        values = label_values(raw.get("labels"))
        return CaseSummary(
            id=case_id,
            check=str(raw.get("check") or "unknown"),
            split=self._splits.get(case_id),
            status=status,
            ambiguous=raw.get("ambiguous") is True,
            labelled=sum(value is not None for value in values),
            total=len(values),
            reason=reason,
        )
