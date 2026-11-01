"""The metrics compare.py reports on, for a check and for one origin of a check."""

from __future__ import annotations

from bench_check_metrics import BinaryMetrics, CategoryMetrics, CheckMetrics


def headline(metrics: CheckMetrics) -> dict[str, float | None]:
    """The metrics compare reports on, by name. Binary-view metrics are `<view>.<metric>`."""
    values: dict[str, float | None] = {
        "coverage": metrics.coverage.coverage.value,
        "item_accuracy": metrics.item_accuracy.value,
        "effective_item_accuracy": metrics.effective.item_accuracy.value,
        "case_accuracy": metrics.case_accuracy.value,
        **_view_values(metrics.binary),
    }
    values["latency_median_s"] = metrics.latency.median_s
    values["tokens_per_case"] = metrics.usage.tokens_per_case
    if metrics.claim_coverage is not None:
        values["claim_coverage"] = metrics.claim_coverage.value
    return values


def origin_headline(metrics: CategoryMetrics) -> dict[str, float | None]:
    """The metrics compare reports on for one origin of a check."""
    return {
        "coverage": metrics.coverage.coverage.value,
        "item_accuracy": metrics.item_accuracy.value,
        "effective_item_accuracy": metrics.effective.item_accuracy.value,
        **_view_values(metrics.binary),
    }


def _view_values(binary: dict[str, BinaryMetrics]) -> dict[str, float | None]:
    values: dict[str, float | None] = {}
    for name, view in binary.items():
        values[f"{name}.precision"] = view.precision.value
        values[f"{name}.recall"] = view.recall.value
        values[f"{name}.effective_recall"] = view.effective_recall.value
        values[f"{name}.f1"] = view.f1
        values[f"{name}.false_positive_rate"] = view.false_positive_rate.value
        values[f"{name}.false_negative_rate"] = view.false_negative_rate.value
    return values
