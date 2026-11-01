"""The adjudication log: how each disagreement was settled, bound to the run it was settled on.

The log is append-only. A correction is a new entry whose `replaces` names the entry it
supersedes (by `entry_id`); merge applies the newest entry of each chain and ignores the rest.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from bench_annotations import Dimension, ItemKey, label_items, run_sha256
from bench_cases import Case

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
    """For an owner ruling, the rulings-log entry it follows. Required for owner rulings."""
    run_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    """The run it was settled on. If the run is edited later, the entry is stale and ignored."""
    labels: dict[str, str] | None = None
    """For a discussion, each annotator's label for the item when it was settled. If any of
    them changes later, the entry is stale and ignored. Owner rulings don't record it."""
    replaces: str | None = None
    """The `entry_id` of the earlier entry for the same item that this one supersedes."""
    settled_at: str | None = None
    """When it was recorded (UTC, ISO 8601)."""

    @model_validator(mode="after")
    def _consistent(self) -> Adjudication:
        if self.how == "owner_ruling" and not (self.ruling or "").strip():
            raise ValueError("an owner ruling must name its rulings-log entry in `ruling`")
        if self.labels is not None and set(self.labels) != set(self.decided_by):
            raise ValueError("a discussion's `labels` must come from exactly its `decided_by`")
        return self

    @property
    def key(self) -> ItemKey:
        return (self.dimension, self.subject)

    @property
    def entry_id(self) -> str:
        """Identifies this entry, so a later one can name it in `replaces`."""
        return hashlib.sha256(self.to_line().encode()).hexdigest()[:16]

    def to_line(self) -> str:
        return self.model_dump_json(exclude_none=True)

    def describe(self) -> str:
        return f"{self.case_id} {self.dimension} {self.subject!r}"


Settled = dict[tuple[str, ItemKey], Adjudication]
"""(case id, item) -> the current adjudication that settles it."""


class IndexedAdjudications(BaseModel):
    settled: Settled
    stale: list[Adjudication]
    """Entries settled on an older version of their case's run; never applied."""


def load_adjudications(path: Path) -> list[Adjudication]:
    if not path.is_file():
        return []
    return parse_adjudications(path, path.read_text(encoding="utf-8"))


def parse_adjudications(path: Path, text: str) -> list[Adjudication]:
    entries: list[Adjudication] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entries.append(Adjudication.model_validate_json(line))
        except ValidationError as exc:
            raise ValueError(f"{path}:{number}: invalid adjudication\n{exc}") from exc
    return entries


def index_adjudications(
    adjudications: list[Adjudication], cases: dict[str, Case]
) -> IndexedAdjudications:
    """Split the log into current and stale entries, dropping every replaced entry.

    Raises ValueError if an entry names no current item, two current entries settle one item,
    or a `replaces` names no earlier entry for the same item, or one already replaced.
    """
    errors: list[str] = []
    replaced = _replaced(adjudications, errors)
    settled: Settled = {}
    stale: list[Adjudication] = []
    for position, x in enumerate(adjudications):
        if position in replaced:
            continue
        case = cases.get(x.case_id)
        if case is None or x.key not in label_items(case.expected):
            errors.append(f"{x.describe()} matches no item of any case")
        elif x.run_sha256 != run_sha256(case):
            stale.append(x)
        elif (x.case_id, x.key) in settled:
            errors.append(f"{x.describe()} is settled more than once")
        else:
            settled[(x.case_id, x.key)] = x
    if errors:
        raise ValueError("invalid adjudications:\n  " + "\n  ".join(errors))
    return IndexedAdjudications(settled=settled, stale=stale)


def _replaced(adjudications: list[Adjudication], errors: list[str]) -> set[int]:
    """Positions of the entries a later entry replaces; adds each broken `replaces` to errors."""
    positions: dict[str, int] = {}
    replaced: set[int] = set()
    for position, x in enumerate(adjudications):
        if x.replaces is not None:
            target = positions.get(x.replaces)
            if target is None:
                errors.append(f"{x.describe()} replaces {x.replaces}, no earlier entry")
            elif adjudications[target].describe() != x.describe():
                errors.append(f"{x.describe()} replaces {x.replaces}, an entry for another item")
            elif target in replaced:
                errors.append(f"{x.describe()} replaces {x.replaces}, which is already replaced")
            else:
                replaced.add(target)
        positions.setdefault(x.entry_id, position)
    return replaced
