"""Turn two or more annotators' labels, plus the adjudication log, into confirmed case labels."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from bench_adjudications import Adjudication, Settled, index_adjudications
from bench_annotations import Annotation, Annotations, ItemKey, label_items
from bench_cases import Case, FaithfulnessExpected


class MergeOutcome(BaseModel):
    confirmed: dict[str, Case]
    unresolved: dict[str, list[str]]
    """Case id -> why it can't be confirmed yet."""
    stale_adjudications: list[Adjudication]
    """Log entries settled on an older version of their run; ignored. Settle the case again."""


def merge(
    annotations: Annotations, cases: dict[str, Case], adjudications: list[Adjudication]
) -> MergeOutcome:
    """Confirm every case at least two annotators labelled and whose disagreements are settled.

    Adjudications settled on an older version of a run are never applied; they are returned in
    `stale_adjudications`. Raises ValueError if an adjudication names no current item or two
    current ones settle the same item.
    """
    indexed = index_adjudications(adjudications, cases)
    by_case: dict[str, dict[str, Annotation]] = {}
    for annotator, labelled in annotations.items():
        for case_id, annotation in labelled.items():
            by_case.setdefault(case_id, {})[annotator] = annotation
    confirmed: dict[str, Case] = {}
    unresolved: dict[str, list[str]] = {}
    for case_id in sorted(by_case):
        result = _merge_case(cases[case_id], by_case[case_id], indexed.settled)
        if isinstance(result, Case):
            confirmed[case_id] = result
        else:
            unresolved[case_id] = result
    return MergeOutcome(
        confirmed=confirmed, unresolved=unresolved, stale_adjudications=indexed.stale
    )


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
            problem = _adjudication_problem(adjudication, labelled, unanimous=unanimous)
            if problem is not None:
                problems.append(problem)
                continue
            final[key] = adjudication.label
            used.append(adjudication)
        elif unanimous:
            final[key] = next(iter(given.values()))
        else:
            votes = ", ".join(f"{name} {label}" for name, label in sorted(given.items()))
            problems.append(f"{key[0]} {key[1]!r} is unsettled ({votes})")
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


def _adjudication_problem(
    x: Adjudication, labelled: dict[str, Annotation], *, unanimous: bool
) -> str | None:
    what = f"the adjudication of {x.dimension} {x.subject!r}"
    if x.how == "discussion":
        if unanimous:
            return f"{what} overrides a label every annotator agreed on; only an owner ruling can"
        outsiders = sorted(set(x.decided_by) - set(labelled))
        if outsiders:
            return f"{what} is a discussion but {', '.join(outsiders)} didn't label this case"
        absent = sorted(set(labelled) - set(x.decided_by))
        if absent:
            return f"{what} is a discussion without {', '.join(absent)}, who labelled this case"
    return None


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
