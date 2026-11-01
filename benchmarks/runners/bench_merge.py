"""Turn two or more annotators' labels, plus the adjudication log, into confirmed case labels."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from bench_adjudications import Adjudication, Settled, index_adjudications
from bench_annotations import Annotation, Annotations, ItemKey, label_items
from bench_cases import Case, FaithfulnessExpected


class StaleAdjudication(BaseModel):
    entry: Adjudication
    reason: str


class MergeOutcome(BaseModel):
    confirmed: dict[str, Case]
    unresolved: dict[str, list[str]]
    """Case id -> why it can't be confirmed yet."""
    stale_adjudications: list[StaleAdjudication]
    """Log entries that no longer describe their item, and why; ignored. Settle it again."""


def merge(
    annotations: Annotations, cases: dict[str, Case], adjudications: list[Adjudication]
) -> MergeOutcome:
    """Confirm every case at least two annotators labelled and whose disagreements are settled.

    Adjudications settled on an older version of a run are never applied, and neither is a
    discussion settled on labels the annotators no longer give (an owner ruling stands whatever
    the labels); both are returned in `stale_adjudications`. Raises ValueError if an
    adjudication names no current item or two current ones settle the same item.
    """
    indexed = index_adjudications(adjudications, cases)
    by_case: dict[str, dict[str, Annotation]] = {}
    for annotator, labelled in annotations.items():
        for case_id, annotation in labelled.items():
            by_case.setdefault(case_id, {})[annotator] = annotation
    stale = [StaleAdjudication(entry=x, reason=RUN_CHANGED) for x in indexed.stale]
    settled: Settled = {}
    for (case_id, key), x in indexed.settled.items():
        reason = _labels_changed(x, by_case.get(case_id, {}))
        if reason is None:
            settled[(case_id, key)] = x
        else:
            stale.append(StaleAdjudication(entry=x, reason=reason))
    confirmed: dict[str, Case] = {}
    unresolved: dict[str, list[str]] = {}
    for case_id in sorted(by_case):
        result = _merge_case(cases[case_id], by_case[case_id], settled)
        if isinstance(result, Case):
            confirmed[case_id] = result
        else:
            unresolved[case_id] = result
    return MergeOutcome(confirmed=confirmed, unresolved=unresolved, stale_adjudications=stale)


RUN_CHANGED = "the run changed after it was settled; settle it again"


def _labels_changed(x: Adjudication, labelled: dict[str, Annotation]) -> str | None:
    """Why a discussion no longer settles its item, or None. Owner rulings never go stale here.

    A case nobody has current labels for isn't merged, so its entries aren't checked."""
    if x.how != "discussion" or not labelled:
        return None
    if x.labels is None:
        return "it doesn't record the labels it settled; settle it again with --replace"
    now = {name: label_items(a.labels)[x.key] for name, a in labelled.items()}
    if now == x.labels:
        return None
    return (
        f"the labels changed after it was settled (then {_votes(x.labels)}, now {_votes(now)}); "
        "settle it again with --replace"
    )


def _votes(labels: dict[str, str]) -> str:
    return ", ".join(f"{name} {label}" for name, label in sorted(labels.items()))


def _merge_case(
    case: Case,
    labelled: dict[str, Annotation],
    settled: Settled,
) -> Case | list[str]:
    if len(labelled) < 2:
        return [f"only {', '.join(labelled)} has labelled it; it needs two annotators"]
    ambiguous = sorted(name for name, x in labelled.items() if x.ambiguous)
    if ambiguous:
        return [f"marked ambiguous by {', '.join(ambiguous)}: drop the case or rewrite the run"]
    items = {name: label_items(x.labels) for name, x in labelled.items()}
    final: dict[ItemKey, str] = {}
    problems: list[str] = []
    used: list[Adjudication] = []
    for key in label_items(case.expected):
        given = {name: labels[key] for name, labels in items.items()}
        adjudication = settled.get((case.id, key))
        agreed = set(given.values())
        unanimous = len(agreed) == 1
        if adjudication is not None and unanimous and adjudication.label in agreed:
            adjudication = None
        if adjudication is not None:
            if adjudication.how == "discussion" and unanimous:
                problems.append(
                    f"the adjudication of {key[0]} {key[1]!r} overrides a label every annotator "
                    "agreed on; only an owner ruling can"
                )
                continue
            final[key] = adjudication.label
            used.append(adjudication)
        elif unanimous:
            final[key] = next(iter(given.values()))
        else:
            problems.append(f"{key[0]} {key[1]!r} is unsettled ({_votes(given)})")
    if problems:
        return problems
    try:
        expected = _with_labels(case, final)
    except ValidationError as exc:
        return [f"an adjudicated label isn't valid for this check: {exc.errors()[0]['msg']}"]
    return case.model_copy(
        update={
            "expected": expected,
            "label_status": "confirmed",
            "annotators": sorted(labelled),
            "notes": _notes(labelled, used),
        }
    )


def _with_labels(case: Case, final: dict[ItemKey, str]) -> Any:
    data = case.expected.model_dump(mode="json", exclude_none=True)
    if isinstance(case.expected, FaithfulnessExpected):
        for claim in data["claims"]:
            claim["label"] = final[("claim", claim["text"])]
        if case.expected.run_label is not None:
            data["run_label"] = _run_label([claim["label"] for claim in data["claims"]])
    elif "calls" in data:
        for call in data["calls"]:
            for dimension in ("verdict", "recovery"):
                if dimension in call:
                    call[dimension] = final[(dimension, f"step {call['step']}")]
    else:
        data["label"] = final[("label", "run")]
    return type(case.expected).model_validate(data)


def _run_label(claims: list[str]) -> str:
    """attest's documented default policy applied to the claim labels."""
    if "unsupported" in claims:
        return "block"
    if "supported" not in claims:
        return "review"
    return "pass"


def _notes(labelled: dict[str, Annotation], used: list[Adjudication]) -> str:
    parts = [f"{name}: {x.rationale.strip()}" for name, x in sorted(labelled.items())]
    for x in used:
        how = "settled by discussion" if x.how == "discussion" else f"owner ruling {x.ruling or ''}"
        parts.append(f"{x.dimension} {x.subject!r} {how.strip()}: {x.reason.strip()}")
    return " | ".join(parts)
