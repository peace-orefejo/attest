from __future__ import annotations

import pytest

from attest import wilson_interval
from bench_cases import BINARY_VIEWS, LABELS
from bench_check_metrics import Prices, binary_metrics, check_metrics
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

SUPPORTED_ONLY = frozenset({"supported"})
TOOL_CLEAN = BINARY_VIEWS["tool_use"][0].negative

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


def test_detection_matches_hand_count() -> None:
    # positives: unsupported, unverifiable (5 items); flagged: unverifiable/unsupported preds.
    # tp: (unsup,unsup)x2 + (unver,unver) = 3; fn: (unsup,sup) + (unver,missing) = 2
    # fp: (sup,unver) = 1; tn: (sup,sup)x3 = 3
    found = detection(PAIRS, SUPPORTED_ONLY)
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
    found = detection([("supported", "supported")], SUPPORTED_ONLY)
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
    found = detection(pairs, TOOL_CLEAN)
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


def test_check_metrics_grade_only_graded_rows_and_break_down_by_category() -> None:
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
            status="errored",
            items=[item("k0", "supported", "error")],
            error="boom",
        ),
    ]
    metrics = check_metrics("faithfulness", rows, Prices(input=1.0, output=10.0))
    covered = metrics.coverage
    assert (covered.attempted, covered.graded, covered.errored, covered.not_run) == (4, 3, 1, 0)
    assert metrics.draft_cases == 3
    assert (metrics.items, metrics.attempted_items) == (4, 5)
    assert metrics.case_accuracy.successes == 2
    sufficiency = metrics.per_category["known_hallucination"].binary["evidence_sufficiency"]
    assert sufficiency.recall.value == 0.5
    assert metrics.per_category["supported_claim"].item_accuracy.value == 1.0
    assert metrics.per_category["supported_claim"].effective.item_accuracy.value == 2 / 3
    assert metrics.claim_coverage is not None and metrics.claim_coverage.value == 1.0
    assert metrics.run_label_accuracy is not None and metrics.run_label_accuracy.n == 1
    assert metrics.usage.calls == 3
    assert metrics.usage.cost_usd == pytest.approx((300 * 1.0 + 30 * 10.0) / 1_000_000)


def test_faithfulness_has_two_named_binary_views_on_a_known_matrix() -> None:
    views = binary_metrics("faithfulness", [_row("a", "x", PAIRS)])
    assert list(views) == ["contradiction_detection", "evidence_sufficiency"]

    # contradiction: positive = unsupported only; unverifiable on either side is negative.
    # tp (unsup,unsup)x2; fn (unsup,sup); fp none; tn the other 6 (incl. (sup,unver),
    # (unver,unver), (unver,missing)).
    contradiction = views["contradiction_detection"]
    assert contradiction.positive == ["unsupported"]
    assert contradiction.negative == ["supported", "unverifiable"]
    assert (contradiction.tp, contradiction.fp, contradiction.fn, contradiction.tn) == (2, 0, 1, 6)
    assert contradiction.precision.value == 1.0
    assert contradiction.recall.value == pytest.approx(2 / 3)
    assert contradiction.f1 == pytest.approx(4 / 5)
    assert contradiction.false_positive_rate.value == 0.0
    assert contradiction.false_negative_rate.value == pytest.approx(1 / 3)
    low, high = wilson_interval(2, 3).low, wilson_interval(2, 3).high
    assert (contradiction.recall.low, contradiction.recall.high) == (low, high)
    assert (contradiction.false_positive_rate.successes, contradiction.false_positive_rate.n) == (
        0,
        6,
    )

    # sufficiency: positive = unsupported + unverifiable (the old single view).
    sufficiency = views["evidence_sufficiency"]
    assert sufficiency.positive == ["unsupported", "unverifiable"]
    assert sufficiency.negative == ["supported"]
    assert (sufficiency.tp, sufficiency.fp, sufficiency.fn, sufficiency.tn) == (3, 1, 2, 3)
    assert sufficiency.precision.value == pytest.approx(3 / 4)
    assert sufficiency.recall.value == pytest.approx(3 / 5)
    assert sufficiency.f1 == pytest.approx(6 / 9)
    assert sufficiency.false_positive_rate.value == pytest.approx(1 / 4)
    assert sufficiency.false_negative_rate.value == pytest.approx(2 / 5)
    interval = wilson_interval(1, 4)
    assert (sufficiency.false_positive_rate.low, sufficiency.false_positive_rate.high) == (
        interval.low,
        interval.high,
    )


def test_other_checks_keep_one_violation_view() -> None:
    for check in ("tool_use", "recovery", "prompt_injection", "role_adherence"):
        assert [view.name for view in BINARY_VIEWS[check]] == ["violation_detection"]
    assert BINARY_VIEWS["role_adherence"][0].positive(LABELS["role_adherence"]) == [
        "out_of_scope_complied"
    ]
