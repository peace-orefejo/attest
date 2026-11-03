"""The labelling page's JSON API, apart from HTTP: state, one case, save, create, help.

GET  /api/state            this annotator's files, their status, and what can be created
GET  /api/help             the guidelines, rendered
GET  /api/case/<id>        one case: the run and this annotator's labels
PUT  /api/case/<id>        save labels (partial work allowed)
POST /api/templates        write blank label files for chosen checks and splits
"""

from __future__ import annotations

from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from bench_annotations import AnnotationError
from bench_cases import CHECKS, SPLITS, Case, Split
from bench_load import Datasets
from label_ui_help import HelpSection, help_sections
from label_ui_store import CaseSummary, LabelStore

CASE_PREFIX = "/api/case/"


class ErrorBody(BaseModel):
    error: str


class Reply(BaseModel):
    status: int = HTTPStatus.OK
    body: BaseModel


class State(BaseModel):
    annotator: str
    folder: str
    cases: list[CaseSummary]
    available: dict[str, dict[str, int]]
    """Check -> split -> how many cases the datasets hold, for creating label files."""
    regenerate: str
    """The command that rewrites a deleted label file."""


class HelpDoc(BaseModel):
    sections: list[HelpSection]


class LabelApi:
    def __init__(
        self,
        annotator: str,
        store: LabelStore,
        available: dict[str, dict[str, int]],
        help_doc: list[HelpSection],
        regenerate: str,
    ) -> None:
        self.annotator = annotator
        self.store = store
        self._available = available
        self._help = HelpDoc(sections=help_doc)
        self._regenerate = regenerate

    def handle(self, method: str, path: str, body: object) -> Reply:
        if method == "GET" and path == "/api/state":
            return Reply(body=self.state())
        if method == "GET" and path == "/api/help":
            return Reply(body=self._help)
        if method == "POST" and path == "/api/templates":
            return self._create(body)
        if path.startswith(CASE_PREFIX) and method in ("GET", "PUT"):
            return self._case(method, path.removeprefix(CASE_PREFIX), body)
        return _error(HTTPStatus.NOT_FOUND, "not found")

    def state(self) -> State:
        return State(
            annotator=self.annotator,
            folder=str(self.store.folder),
            cases=self.store.summaries(),
            available=self._available,
            regenerate=self._regenerate,
        )

    def _case(self, method: str, case_id: str, body: object) -> Reply:
        if method == "GET":
            case = self.store.case(case_id)
            return Reply(body=case) if case else _error(HTTPStatus.NOT_FOUND, "no such case")
        if not isinstance(body, dict):
            return _error(HTTPStatus.BAD_REQUEST, "send a JSON object")
        fields: dict[str, Any] = dict(body)  # pyright: ignore[reportUnknownArgumentType]
        version = fields.pop("version", None)
        try:
            result = self.store.save(case_id, fields, version)
        except AnnotationError as exc:
            return _error(HTTPStatus.FORBIDDEN, str(exc))
        if result is None:
            return _error(HTTPStatus.NOT_FOUND, "no such case")
        status = HTTPStatus.OK if result.saved else HTTPStatus.UNPROCESSABLE_ENTITY
        return Reply(status=status, body=result)

    def _create(self, body: object) -> Reply:
        checks = _chosen(body, "checks", CHECKS)
        splits = _chosen(body, "splits", SPLITS)
        if not checks or not splits:
            return _error(HTTPStatus.BAD_REQUEST, "choose at least one check and one split")
        try:
            result = self.store.create(
                [check for check in CHECKS if check in checks],
                [split for split in SPLITS if split in splits],
            )
        except AnnotationError as exc:
            return _error(HTTPStatus.FORBIDDEN, str(exc))
        return Reply(body=result)


def build_api(
    annotator: str,
    folder: Path,
    datasets: Datasets,
    *,
    forbidden: Callable[[Path], bool] | None,
    regenerate: str,
) -> LabelApi:
    """The API for `annotator`'s own label folder, with the guidelines read now."""
    cases: dict[str, Case] = {}
    splits: dict[str, Split] = {}
    available: dict[str, dict[str, int]] = {}
    for check, by_split in datasets.cases.items():
        for split, split_cases in by_split.items():
            available.setdefault(check, {})[split] = len(split_cases)
            for case in split_cases:
                cases[case.id] = case
                splits[case.id] = split
    store = LabelStore(folder, cases, splits, forbidden)
    return LabelApi(annotator, store, available, help_sections(), regenerate)


def _chosen(body: object, key: str, allowed: tuple[str, ...]) -> list[str]:
    if not isinstance(body, dict):
        return []
    fields: dict[str, object] = body  # pyright: ignore[reportUnknownVariableType]
    values = fields.get(key)
    if not isinstance(values, list):
        return []
    items: list[object] = values  # pyright: ignore[reportUnknownVariableType]
    return [item for item in allowed if item in items]


def _error(status: int, message: str) -> Reply:
    return Reply(status=status, body=ErrorBody(error=message))
