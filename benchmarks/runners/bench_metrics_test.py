from __future__ import annotations

import pytest

from attest import wilson_interval
from bench_cases import CLEAN_LABELS, LABELS
from bench_check_metrics import Prices, check_metrics
from bench_metrics import (
    accuracy,
    claim_coverage,
    confusion,
    cost_usd,
    detection,
    latency,
    nearest_rank,
    per_label,
    rate,
)
from bench_rows import CaseRow, CaseUsage, item

# Faithfulness pairs (expected, predicted), counted by hand:
#   supported   -> supported x3, unverifiable x1
#   unsupported -> unsupported x2, supported x1
#   unverifiable-> unverifiable x1, missing x1
PAIRS = [
    ("supported", "supported"),
    ("supported", "supported"),
    ("supported", "supported"),
    ("supported", "unverifiable"),
    ("unsupported", "unsupported"),
    ("unsupported", "unsupported"),
    ("unsupported", "supported"),
    ("unverifiable", "unverifiable"),
    ("unverifiable", "missing"),
]


def test_confusion_matrix_matches_hand_count() -> None:
    result = confusion(PAIRS, LABELS["faithfulness"])
    assert result.labels == ["supported", "unsupported", "unverifiable", "missing"]
    assert result.matrix["supported"] == {
        "supported": 3,
        "unsupported": 0,
        "unverifiable": 1,
        "missing": 0,
    }
    assert result.matrix["unsupported"] == {
        "supported": 1,
        "unsupported": 2,
        "unverifiable": 0,
        "missing": 0,
    }
    assert result.matrix["unverifiable"]["unverifiable"] == 1
    assert result.matrix["unverifiable"]["missing"] == 1
    assert sum(sum(row.values()) for row in result.matrix.values()) == len(PAIRS)


def test_violation_detection_matches_hand_count() -> None:
    # positives: unsupported, unverifiable (5 items); flagged: unverifiable/unsupported preds.
    # tp: (unsup,unsup)x2 + (unver,unver) = 3; fn: (unsup,sup) + (unver,missing) = 2
    # fp: (sup,unver) = 1; tn: (sup,sup)x3 = 3
    found = detection(PAIRS, CLEAN_LABELS["faithfulness"])
    assert (found.tp, found.fp, found.fn, found.tn) == (3, 1, 2, 3)
    assert found.precision.value == pytest.approx(3 / 4)
    assert found.recall.value == pytest.approx(3 / 5)
    assert found.f1 == pytest.approx(2 * 3 / (2 * 3 + 1 + 2))
    assert found.false_positive_rate.value == pytest.approx(1 / 4)
    assert found.false_negative_rate.value == pytest.approx(2 / 5)
    expected = wilson_interval(3, 5)
    assert (found.recall.low, found.recall.high) == (expected.low, expected.high)
    assert (found.recall.successes, found.recall.n) == (3, 5)


def test_per_label_scores() -> None:
    scores = per_label(PAIRS, LABELS["faithfulness"])
    assert scores["unsupported"].support == 3
    assert scores["unsupported"].predicted == 2
    assert scores["unsupported"].precision.value == 1.0
    assert scores["unsupported"].recall.value == pytest.approx(2 / 3)
    assert scores["supported"].precision.value == pytest.approx(3 / 4)


def test_empty_denominators_are_none_not_zero() -> None:
    assert rate(0, 0).value is None
    found = detection([("supported", "supported")], CLEAN_LABELS["faithfulness"])
    assert found.precision.value is None and found.recall.value is None and found.f1 is None
    assert found.false_positive_rate.value == 0.0


def test_accuracy_and_coverage() -> None:
    assert accuracy(PAIRS).successes == 6
    coverage = claim_coverage(p for _, p in PAIRS)
    assert (coverage.successes, coverage.n) == (6, 9)


def test_multiclass_tool_use_confusion() -> None:
    pairs = [
        ("correct", "correct"),
        ("error_claimed_success", "error_silent"),
        ("disallowed_tool", "disallowed_tool"),
        ("correct", "error_silent"),
    ]
    matrix = confusion(pairs, LABELS["tool_use"]).matrix
    assert matrix["error_claimed_success"]["error_silent"] == 1
    assert matrix["correct"]["error_silent"] == 1
    found = detection(pairs, CLEAN_LABELS["tool_use"])
    assert (found.tp, found.fp, found.fn, found.tn) == (2, 1, 0, 1)


def test_latency_percentiles() -> None:
    values = [float(v) for v in range(1, 21)]
    result = latency(values)
    assert result.median_s == 10.5
    assert result.p95_s == 19.0
    assert nearest_rank([1.0, 2.0, 3.0], 0.5) == 2.0
    assert latency([]).median_s is None


def test_cost_needs_both_prices() -> None:
    assert cost_usd(2_000_000, 1_000_000, None, 15.0) is None
    assert cost_usd(2_000_000, 1_000_000, 3.0, 15.0) == pytest.approx(21.0)


def _row(
    id_: str,
    category: str,
    pairs: list[tuple[str, str]],
    run_expected: str | None = None,
    run_predicted: str | None = None,
) -> CaseRow:
    items = [item(f"k{i}", e, p) for i, (e, p) in enumerate(pairs)]
    return CaseRow(
        id=id_,
        check="faithfulness",
        category=category,
        source="synthetic",
        label_status="draft",
        items=items,
        correct=all(i.correct for i in items),
        latency_s=1.0,
        usage=CaseUsage(calls=1, input_tokens=100, output_tokens=10),
        run_expected=run_expected,
        run_predicted=run_predicted,
    )


def test_check_metrics_skip_errored_rows_and_break_down_by_category() -> None:
    rows = [
        _row(
            "a",
            "known_hallucination",
            [("unsupported", "unsupported")],
            run_expected="block",
            run_predicted="block",
        ),
        _row("b", "known_hallucination", [("unsupported", "supported")]),
        _row("c", "supported_claim", [("supported", "supported"), ("supported", "supported")]),
        CaseRow(
            id="d",
            check="faithfulness",
            category="supported_claim",
            source="synthetic",
            label_status="confirmed",
            error="boom",
        ),
    ]
    metrics = check_metrics("faithfulness", rows, Prices(input=1.0, output=10.0))
    assert (metrics.cases, metrics.graded_cases, metrics.errored_cases) == (4, 3, 1)
    assert metrics.draft_cases == 3
    assert metrics.items == 4
    assert metrics.case_accuracy.successes == 2
    assert metrics.per_category["known_hallucination"].detection.recall.value == 0.5
    assert metrics.per_category["supported_claim"].item_accuracy.value == 1.0
    assert metrics.claim_coverage is not None and metrics.claim_coverage.value == 1.0
    assert metrics.run_label_accuracy is not None and metrics.run_label_accuracy.n == 1
    assert metrics.usage.calls == 3
    assert metrics.usage.cost_usd == pytest.approx((300 * 1.0 + 30 * 10.0) / 1_000_000)
