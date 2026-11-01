"""Aggregate one check's case rows into its metrics."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence

from pydantic import BaseModel, Field

from bench_cases import BINARY_VIEWS, LABELS, BinaryView, CheckName
from bench_coverage import Coverage, EffectiveAccuracy, coverage, effective_accuracy
from bench_metrics import (
    Confusion,
    Detection,
    LabelScore,
    Latency,
    Pair,
    Rate,
    accuracy,
    claim_coverage,
    confusion,
    cost_usd,
    detection,
    latency,
    per_label,
    rate,
)
from bench_rows import CaseRow, CaseUsage


class Prices(BaseModel):
    """US dollars per million tokens. Input tokens include cached ones."""

    input: float | None = None
    output: float | None = None


class BinaryMetrics(Detection):
    """One named binary view over graded items, plus its recall over every attempted item
    (errored and not-run items count as missed)."""

    question: str
    positive: list[str]
    negative: list[str]
    effective_recall: Rate


class CategoryMetrics(BaseModel):
    """One group's metrics within a check: a category's, or an origin's."""

    coverage: Coverage
    item_accuracy: Rate
    effective: EffectiveAccuracy
    binary: dict[str, BinaryMetrics]


class UsageTotals(BaseModel):
    calls: int
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    cache_hits: int
    tokens_per_case: float | None
    cost_usd: float | None


class CheckMetrics(BaseModel):
    """Metrics for one check. Items are claims (faithfulness), tool calls (tool_use, recovery)
    or runs (prompt_injection, role_adherence).

    `item_accuracy`, `case_accuracy`, the confusion matrix and the binary views count graded
    cases only; `effective` and each view's `effective_recall` count every attempted case,
    with errored and not-run items as wrong. Read either beside `coverage`."""

    item_unit: str
    coverage: Coverage
    draft_cases: int
    items: int
    """Labelled items in graded cases."""
    attempted_items: int
    item_accuracy: Rate
    case_accuracy: Rate
    effective: EffectiveAccuracy
    confusion: Confusion
    binary: dict[str, BinaryMetrics]
    per_label: dict[str, LabelScore]
    per_category: dict[str, CategoryMetrics]
    per_origin: dict[str, CategoryMetrics] = Field(default_factory=dict[str, CategoryMetrics])
    """The same breakdown as `per_category`, by the cases' origin (such as `attest-seed`)."""
    claim_coverage: Rate | None = None
    run_label_accuracy: Rate | None = None
    latency: Latency
    usage: UsageTotals


ITEM_UNITS: dict[CheckName, str] = {
    "faithfulness": "claim",
    "tool_use": "tool call",
    "recovery": "tool call",
    "prompt_injection": "run",
    "role_adherence": "run",
}


def check_metrics(check: CheckName, rows: Sequence[CaseRow], prices: Prices) -> CheckMetrics:
    graded = [row for row in rows if row.graded]
    pairs = _pairs(graded)
    run_pairs = [
        (row.run_expected, row.run_predicted)
        for row in graded
        if row.run_expected is not None and row.run_predicted is not None
    ]
    return CheckMetrics(
        item_unit=ITEM_UNITS[check],
        coverage=coverage(rows),
        draft_cases=sum(row.label_status == "draft" for row in rows),
        items=len(pairs),
        attempted_items=len(_pairs(rows)),
        item_accuracy=accuracy(pairs),
        case_accuracy=rate(sum(bool(row.correct) for row in graded), len(graded)),
        effective=effective_accuracy(rows),
        confusion=confusion(pairs, LABELS[check]),
        binary=binary_metrics(check, rows),
        per_label=per_label(pairs, LABELS[check]),
        per_category=_breakdown(check, rows, lambda row: row.category),
        per_origin=_breakdown(check, rows, lambda row: row.origin or "unknown"),
        claim_coverage=claim_coverage(p for _, p in pairs) if check == "faithfulness" else None,
        run_label_accuracy=accuracy(run_pairs) if run_pairs else None,
        latency=latency([row.latency_s for row in graded if row.latency_s is not None]),
        usage=_usage(rows, prices),
    )


def binary_metrics(check: CheckName, rows: Sequence[CaseRow]) -> dict[str, BinaryMetrics]:
    """Every binary view of `check`, keyed by name."""
    graded = _pairs([row for row in rows if row.graded])
    attempted = _pairs(rows)
    return {view.name: _view(check, view, graded, attempted) for view in BINARY_VIEWS[check]}


def _view(
    check: CheckName, view: BinaryView, graded: Sequence[Pair], attempted: Sequence[Pair]
) -> BinaryMetrics:
    return BinaryMetrics(
        **detection(graded, view.negative).model_dump(),
        question=view.question,
        positive=view.positive(LABELS[check]),
        negative=[label for label in LABELS[check] if label in view.negative],
        effective_recall=detection(attempted, view.negative).recall,
    )


def _pairs(rows: Sequence[CaseRow]) -> list[Pair]:
    return [(item.expected, item.predicted) for row in rows for item in row.items]


def _breakdown(
    check: CheckName, rows: Sequence[CaseRow], key: Callable[[CaseRow], str]
) -> dict[str, CategoryMetrics]:
    """Coverage, accuracy and the binary views per group of rows, such as per category."""
    groups: dict[str, list[CaseRow]] = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    return {
        group: CategoryMetrics(
            coverage=coverage(members),
            item_accuracy=accuracy(_pairs([row for row in members if row.graded])),
            effective=effective_accuracy(members),
            binary=binary_metrics(check, members),
        )
        for group, members in sorted(groups.items())
    }


def _usage(rows: Sequence[CaseRow], prices: Prices) -> UsageTotals:
    total = CaseUsage(
        calls=sum(row.usage.calls for row in rows),
        input_tokens=sum(row.usage.input_tokens for row in rows),
        output_tokens=sum(row.usage.output_tokens for row in rows),
        cached_input_tokens=sum(row.usage.cached_input_tokens for row in rows),
        cache_hits=sum(row.usage.cache_hits for row in rows),
    )
    tokens = total.input_tokens + total.output_tokens
    return UsageTotals(
        **total.model_dump(),
        tokens_per_case=tokens / len(rows) if rows else None,
        cost_usd=cost_usd(total.input_tokens, total.output_tokens, prices.input, prices.output),
    )
