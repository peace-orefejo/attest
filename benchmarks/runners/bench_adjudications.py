"""The adjudication log: how each disagreement was settled, bound to the run it was settled on."""

from __future__ import annotations

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

    @model_validator(mode="after")
    def _ruling_named(self) -> Adjudication:
        if self.how == "owner_ruling" and not (self.ruling or "").strip():
            raise ValueError("an owner ruling must name its rulings-log entry in `ruling`")
        return self

    @property
    def key(self) -> ItemKey:
        return (self.dimension, self.subject)

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
    entries: list[Adjudication] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
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
    """Split the log into current and stale entries.

    Raises ValueError if an entry names no current item or two current entries settle one item.
    """
    settled: Settled = {}
    stale: list[Adjudication] = []
    errors: list[str] = []
    for x in adjudications:
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


def append_adjudication(path: Path, entry: Adjudication, cases: dict[str, Case]) -> None:
    """Add `entry` to the log at `path`, refusing it if the log would become invalid."""
    existing = load_adjudications(path)
    index_adjudications([*existing, entry], cases)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    separator = "\n" if text and not text.endswith("\n") else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as log:
        log.write(separator + entry.model_dump_json(exclude_none=True) + "\n")
