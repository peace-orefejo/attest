"""Aggregate one check's case rows into its metrics."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from pydantic import BaseModel

from bench_cases import CLEAN_LABELS, LABELS, CheckName
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


class CategoryMetrics(BaseModel):
    cases: int
    item_accuracy: Rate
    case_accuracy: Rate
    detection: Detection


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
    or runs (prompt_injection, role_adherence). Errored cases are counted, not scored."""

    item_unit: str
    cases: int
    graded_cases: int
    errored_cases: int
    draft_cases: int
    items: int
    item_accuracy: Rate
    case_accuracy: Rate
    confusion: Confusion
    detection: Detection
    per_label: dict[str, LabelScore]
    per_category: dict[str, CategoryMetrics]
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
        cases=len(rows),
        graded_cases=len(graded),
        errored_cases=len(rows) - len(graded),
        draft_cases=sum(row.label_status == "draft" for row in rows),
        items=len(pairs),
        item_accuracy=accuracy(pairs),
        case_accuracy=rate(sum(bool(row.correct) for row in graded), len(graded)),
        confusion=confusion(pairs, LABELS[check]),
        detection=detection(pairs, CLEAN_LABELS[check]),
        per_label=per_label(pairs, LABELS[check]),
        per_category=_per_category(check, graded),
        claim_coverage=claim_coverage(p for _, p in pairs) if check == "faithfulness" else None,
        run_label_accuracy=accuracy(run_pairs) if run_pairs else None,
        latency=latency([row.latency_s for row in graded if row.latency_s is not None]),
        usage=_usage(rows, prices),
    )


def _pairs(rows: Sequence[CaseRow]) -> list[Pair]:
    return [(item.expected, item.predicted) for row in rows for item in row.items]


def _per_category(check: CheckName, rows: Sequence[CaseRow]) -> dict[str, CategoryMetrics]:
    by_category: dict[str, list[CaseRow]] = defaultdict(list)
    for row in rows:
        by_category[row.category].append(row)
    return {
        category: CategoryMetrics(
            cases=len(members),
            item_accuracy=accuracy(_pairs(members)),
            case_accuracy=rate(sum(bool(row.correct) for row in members), len(members)),
            detection=detection(_pairs(members), CLEAN_LABELS[check]),
        )
        for category, members in sorted(by_category.items())
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
