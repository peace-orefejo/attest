"""Build and record one settlement for `annotate.py settle`, refusing what merge would reject.

A discussion is bound to the labels it settled: settle reads the annotators' current label
files, requires `--by` to name exactly the annotators who labelled the case, requires that
they still disagree, and records each one's label in the entry. If any of those labels later
changes, merge reports the entry as stale and ignores it. An owner ruling records no labels
and stands whatever they become.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from bench_adjudication_log import append_adjudication
from bench_adjudications import Adjudication
from bench_annotations import ANNOTATOR_PATTERN, AnnotationError, Dimension, label_items, run_sha256
from bench_cases import LABELS, Case, CheckName
from bench_label_files import load_annotations


class Settlement(BaseModel):
    """What `settle` was asked to record, before it is checked."""

    dimension: Dimension
    subject: str
    label: str
    how: Literal["discussion", "owner_ruling"]
    decided_by: list[str]
    reason: str
    ruling: str | None = None


def settle(
    case_id: str,
    settlement: Settlement,
    cases: dict[str, Case],
    *,
    labels_root: Path,
    log: Path,
    replace: bool = False,
) -> Adjudication:
    """Check `settlement` against `case_id` and append it to `log`; returns the entry written.

    Raises AnnotationError (or ValueError, from the log) listing every problem found."""
    case = cases.get(case_id)
    if case is None:
        raise AnnotationError(f"{case_id}: no such case")
    s = settlement
    problems = _problems(case, s)
    labels = None
    if s.how == "discussion" and not problems:
        labels = _discussion_labels(case, s, cases, labels_root, problems)
    if problems:
        raise AnnotationError(f"can't settle {case_id}:\n  " + "\n  ".join(problems))
    entry = Adjudication(
        case_id=case.id,
        dimension=s.dimension,
        subject=s.subject,
        label=s.label,
        how=s.how,
        decided_by=s.decided_by,
        reason=s.reason.strip(),
        ruling=s.ruling,
        run_sha256=run_sha256(case),
        labels=labels,
        settled_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    return append_adjudication(log, entry, cases, replace=replace)


def allowed_labels(check: CheckName, dimension: Dimension) -> tuple[str, ...]:
    """The labels a person may give for one kind of item. A recovery case's `verdict` takes
    tool-use labels and its `recovery` takes recovery labels."""
    if dimension == "verdict":
        return LABELS["tool_use"]
    if dimension == "claim":
        return LABELS["faithfulness"]
    return LABELS[check]


def _problems(case: Case, s: Settlement) -> list[str]:
    problems: list[str] = []
    if (s.dimension, s.subject) not in label_items(case.expected):
        items = ", ".join(f"{d} {subject!r}" for d, subject in label_items(case.expected))
        problems.append(f"it has no item {s.dimension} {s.subject!r}; its items are {items}")
    elif s.label not in allowed_labels(case.check, s.dimension):
        allowed = ", ".join(allowed_labels(case.check, s.dimension))
        problems.append(f"{s.label!r} isn't a {case.check} {s.dimension} label ({allowed})")
    bad = [name for name in s.decided_by if not ANNOTATOR_PATTERN.fullmatch(name)]
    if bad:
        problems.append(f"--by names are lowercase initials or ids, such as 'po', not {bad}")
    if not s.reason.strip():
        problems.append("--reason is blank")
    if s.how == "owner_ruling" and not (s.ruling or "").strip():
        problems.append("an owner ruling needs --ruling naming its rulings-log entry")
    return problems


def _discussion_labels(
    case: Case, s: Settlement, cases: dict[str, Case], labels_root: Path, problems: list[str]
) -> dict[str, str] | None:
    """Each annotator's current label for the item, or None after adding why it can't be
    settled by discussion to `problems`."""
    annotations = load_annotations(labels_root, cases).annotations
    given = {
        name: label_items(by_case[case.id].labels)[(s.dimension, s.subject)]
        for name, by_case in annotations.items()
        if case.id in by_case
    }
    if len(given) < 2:
        problems.append(
            f"a discussion settles a disagreement between annotators, but only "
            f"{sorted(given) or 'nobody'} has finished, current labels for it in {labels_root}"
        )
        return None
    if sorted(s.decided_by) != sorted(given):
        problems.append(
            f"--by must name exactly the annotators who labelled it, {' '.join(sorted(given))}"
        )
    if len(set(given.values())) == 1:
        problems.append(
            f"every annotator already gives {next(iter(given.values()))!r}, so there is nothing "
            "to settle; only an owner ruling can override an agreed label"
        )
    return given
