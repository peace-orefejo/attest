"""Turn two or more annotators' labels, plus the adjudication log, into confirmed case labels."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from bench_annotations import Annotation, Annotations, Dimension, ItemKey, label_items
from bench_cases import CHECKS, SPLITS, Case, FaithfulnessExpected
from bench_load import case_file

ADJUDICATIONS_FILE = Path(__file__).resolve().parent.parent / "annotations" / "adjudications.jsonl"


class Adjudication(BaseModel):
    """How one disagreement was settled. Never by looking at what attest said."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    dimension: Dimension
    subject: str
    label: str
    how: Literal["discussion", "owner_ruling"]
    decided_by: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)
    ruling: str | None = None
    """For an owner ruling, the rulings-log entry it follows."""


class MergeOutcome(BaseModel):
    confirmed: dict[str, Case]
    unresolved: dict[str, list[str]]
    """Case id -> why it can't be confirmed yet."""


def load_adjudications(path: Path) -> list[Adjudication]:
    if not path.is_file():
        return []
    entries: list[Adjudication] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entries.append(Adjudication.model_validate_json(line))
        except ValidationError as exc:
            raise ValueError(f"{path}:{number}: invalid adjudication\n{exc}") from exc
    return entries


def merge(
    annotations: Annotations, cases: dict[str, Case], adjudications: list[Adjudication]
) -> MergeOutcome:
    """Confirm every case at least two annotators labelled and whose disagreements are settled."""
    settled: dict[tuple[str, ItemKey], Adjudication] = {
        (x.case_id, (x.dimension, x.subject)): x for x in adjudications
    }
    by_case: dict[str, dict[str, Annotation]] = {}
    for annotator, labelled in annotations.items():
        for case_id, annotation in labelled.items():
            by_case.setdefault(case_id, {})[annotator] = annotation
    confirmed: dict[str, Case] = {}
    unresolved: dict[str, list[str]] = {}
    for case_id in sorted(by_case):
        result = _merge_case(cases[case_id], by_case[case_id], settled)
        if isinstance(result, Case):
            confirmed[case_id] = result
        else:
            unresolved[case_id] = result
    return MergeOutcome(confirmed=confirmed, unresolved=unresolved)


def _merge_case(
    case: Case,
    labelled: dict[str, Annotation],
    settled: dict[tuple[str, ItemKey], Adjudication],
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
        if adjudication is not None:
            final[key] = adjudication.label
            used.append(adjudication)
        elif len(set(given.values())) == 1:
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


def write_cases(root: Path, confirmed: dict[str, Case]) -> int:
    """Replace each confirmed case's line in its case file; returns how many were written."""
    written = 0
    for check in CHECKS:
        for split in SPLITS:
            path = case_file(root, check, split)
            if not path.is_file():
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            changed = False
            for index, line in enumerate(lines):
                if not line.strip():
                    continue
                case_id = json.loads(line)["id"]
                if case_id in confirmed:
                    lines[index] = json.dumps(
                        confirmed[case_id].model_dump(mode="json", exclude_unset=True),
                        ensure_ascii=False,
                    )
                    changed = True
                    written += 1
            if changed:
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return written
