"""How much of a check was actually evaluated, and accuracy that charges for what wasn't."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from bench_metrics import Rate, rate
from bench_rows import CaseRow


class Coverage(BaseModel):
    """Evaluation coverage for one check. `attempted` is every case the run set out to grade:
    graded, errored (the evaluation raised) and not run (the call budget ran out first)."""

    attempted: int
    graded: int
    errored: int
    not_run: int
    coverage: Rate
    """graded / attempted."""
    operational_failure_rate: Rate
    """errored / attempted."""


class EffectiveAccuracy(BaseModel):
    """Accuracy over every attempted case, counting errored and not-run items as wrong."""

    item_accuracy: Rate
    case_accuracy: Rate


def coverage(rows: Sequence[CaseRow]) -> Coverage:
    graded = sum(row.status == "graded" for row in rows)
    errored = sum(row.status == "errored" for row in rows)
    return Coverage(
        attempted=len(rows),
        graded=graded,
        errored=errored,
        not_run=sum(row.status == "not_run" for row in rows),
        coverage=rate(graded, len(rows)),
        operational_failure_rate=rate(errored, len(rows)),
    )


def effective_accuracy(rows: Sequence[CaseRow]) -> EffectiveAccuracy:
    correct_items = sum(item.correct for row in rows if row.graded for item in row.items)
    return EffectiveAccuracy(
        item_accuracy=rate(correct_items, sum(len(row.items) for row in rows)),
        case_accuracy=rate(sum(row.graded and bool(row.correct) for row in rows), len(rows)),
    )
