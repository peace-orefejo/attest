"""Withhold case contents from reports on private datasets, keeping every metric."""

from __future__ import annotations

import hashlib

from bench_rows import CaseRow

WITHHELD_ERROR = "error (details withheld: private dataset)"


def withhold_case_details(rows: list[CaseRow]) -> list[CaseRow]:
    """Replace what could reveal a private case: its id, item keys (such as claim texts) and
    error messages. Labels, predictions, categories, timings and usage stay, so the report's
    metrics are unchanged and each row can still be matched across runs of the same dataset.
    """
    return [_withhold(row) for row in rows]


def private_case_id(case_id: str) -> str:
    return "case-" + hashlib.sha256(case_id.encode()).hexdigest()[:12]


def _withhold(row: CaseRow) -> CaseRow:
    items = [
        item.model_copy(update={"key": f"item-{number}"})
        for number, item in enumerate(row.items, start=1)
    ]
    return row.model_copy(
        update={
            "id": private_case_id(row.id),
            "items": items,
            "error": WITHHELD_ERROR if row.error is not None else None,
        }
    )
