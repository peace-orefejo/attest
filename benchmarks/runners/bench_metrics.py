"""Pure metric functions: confusion matrices, binary detection with Wilson intervals, latency."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from pydantic import BaseModel

from attest import wilson_interval
from bench_rows import UNGRADED_PREDICTIONS

Pair = tuple[str, str]
"""(expected, predicted) for one labelled item."""

CHECKABLE_CLAIM_VERDICTS = frozenset({"supported", "unsupported"})


class Rate(BaseModel):
    """A proportion with its Wilson 95% interval and the counts behind it. `value` is None
    when the denominator is zero."""

    value: float | None
    low: float | None
    high: float | None
    successes: int
    n: int


class Confusion(BaseModel):
    """Counts of predicted labels for each expected label: `matrix[expected][predicted]`."""

    labels: list[str]
    matrix: dict[str, dict[str, int]]


class Detection(BaseModel):
    """One binary view: labels outside the view's negative set are positive."""

    tp: int
    fp: int
    fn: int
    tn: int
    precision: Rate
    recall: Rate
    f1: float | None
    false_positive_rate: Rate
    false_negative_rate: Rate


class LabelScore(BaseModel):
    """One label against the rest."""

    support: int
    predicted: int
    precision: Rate
    recall: Rate
    f1: float | None


class Latency(BaseModel):
    n: int
    median_s: float | None
    p95_s: float | None


def rate(successes: int, n: int) -> Rate:
    if n == 0:
        return Rate(value=None, low=None, high=None, successes=0, n=0)
    interval = wilson_interval(successes, n)
    return Rate(value=interval.rate, low=interval.low, high=interval.high, successes=successes, n=n)


def accuracy(pairs: Sequence[Pair]) -> Rate:
    return rate(sum(expected == predicted for expected, predicted in pairs), len(pairs))


def confusion(pairs: Sequence[Pair], labels: Sequence[str]) -> Confusion:
    """A full matrix over `labels`, plus any other label that was expected or predicted."""
    ordered = _ordered_labels(pairs, labels)
    matrix = {expected: dict.fromkeys(ordered, 0) for expected in ordered}
    for expected, predicted in pairs:
        matrix[expected][predicted] += 1
    return Confusion(labels=ordered, matrix=matrix)


def is_positive(label: str, negative: frozenset[str]) -> bool:
    """A positive label. `missing`, `error` and `not_run` are never a detection."""
    return label not in negative and label not in UNGRADED_PREDICTIONS


def detection(pairs: Sequence[Pair], negative: frozenset[str]) -> Detection:
    tp = fp = fn = tn = 0
    for expected, predicted in pairs:
        actual, flagged = is_positive(expected, negative), is_positive(predicted, negative)
        tp += actual and flagged
        fp += flagged and not actual
        fn += actual and not flagged
        tn += not actual and not flagged
    return Detection(
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=rate(tp, tp + fp),
        recall=rate(tp, tp + fn),
        f1=f1_score(tp, fp, fn),
        false_positive_rate=rate(fp, fp + tn),
        false_negative_rate=rate(fn, fn + tp),
    )


def per_label(pairs: Sequence[Pair], labels: Sequence[str]) -> dict[str, LabelScore]:
    scores: dict[str, LabelScore] = {}
    for label in _ordered_labels(pairs, labels):
        tp = sum(e == label and p == label for e, p in pairs)
        support = sum(e == label for e, _ in pairs)
        predicted = sum(p == label for _, p in pairs)
        scores[label] = LabelScore(
            support=support,
            predicted=predicted,
            precision=rate(tp, predicted),
            recall=rate(tp, support),
            f1=f1_score(tp, predicted - tp, support - tp),
        )
    return scores


def claim_coverage(predicted: Iterable[str]) -> Rate:
    """Share of claims the verifier could check: it said supported or unsupported."""
    labels = list(predicted)
    return rate(sum(label in CHECKABLE_CLAIM_VERDICTS for label in labels), len(labels))


def f1_score(tp: int, fp: int, fn: int) -> float | None:
    denominator = 2 * tp + fp + fn
    return None if denominator == 0 else 2 * tp / denominator


def latency(seconds: Sequence[float]) -> Latency:
    if not seconds:
        return Latency(n=0, median_s=None, p95_s=None)
    ordered = sorted(seconds)
    return Latency(n=len(ordered), median_s=_median(ordered), p95_s=nearest_rank(ordered, 0.95))


def nearest_rank(ordered: Sequence[float], quantile: float) -> float:
    """The nearest-rank percentile of already sorted values."""
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[rank - 1]


def cost_usd(
    input_tokens: int, output_tokens: int, price_in: float | None, price_out: float | None
) -> float | None:
    """Dollar cost from per-million-token prices, or None when no price was given."""
    if price_in is None or price_out is None:
        return None
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


def _median(ordered: Sequence[float]) -> float:
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _ordered_labels(pairs: Sequence[Pair], labels: Sequence[str]) -> list[str]:
    ordered = list(labels)
    for expected, predicted in pairs:
        for label in (expected, predicted):
            if label not in ordered:
                ordered.append(label)
    return ordered
