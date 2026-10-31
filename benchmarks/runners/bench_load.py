"""Load and validate the benchmark datasets, and fingerprint them."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, ValidationError

from bench_cases import CHECKS, SPLITS, Case, CheckName, Split

DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"


class DatasetError(ValueError):
    """A case file is malformed or the datasets break a rule (duplicates, split leaks)."""


class Datasets(BaseModel):
    """Every case of every check and split, validated together."""

    cases: dict[CheckName, dict[Split, list[Case]]]
    version: str

    def split(self, check: CheckName, split: Split) -> list[Case]:
        return self.cases[check][split]


def case_file(root: Path, check: CheckName, split: Split) -> Path:
    return root / check / f"{split}.jsonl"


def load_datasets(root: Path = DATASETS_DIR) -> Datasets:
    """Load every case file under `root`, rejecting anything that breaks a dataset rule.

    Each file must exist (an empty file is fine). Case ids are unique across all files, an id
    may not appear in both dev and held-out, and each case's `check` must match its folder.
    """
    cases: dict[CheckName, dict[Split, list[Case]]] = {
        check: {split: load_file(case_file(root, check, split), check) for split in SPLITS}
        for check in CHECKS
    }
    _reject_split_leaks(cases)
    _reject_duplicate_ids(cases)
    return Datasets(cases=cases, version=dataset_version(root))


def load_file(path: Path, check: CheckName) -> list[Case]:
    """Parse one JSONL case file; every error names the file and line."""
    if not path.is_file():
        raise DatasetError(f"{path}: case file is missing")
    cases: list[Case] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = Case.model_validate_json(line)
        except ValidationError as exc:
            raise DatasetError(f"{path}:{number}: invalid case\n{exc}") from exc
        if case.check != check:
            raise DatasetError(
                f"{path}:{number}: case {case.id!r} has check {case.check!r} "
                f"but lives in the {check!r} folder"
            )
        cases.append(case)
    return cases


def dataset_version(root: Path = DATASETS_DIR) -> str:
    """SHA-256 over every case file's path and bytes, so any edit changes the version."""
    digest = hashlib.sha256()
    for check in CHECKS:
        for split in SPLITS:
            path = case_file(root, check, split)
            digest.update(f"{check}/{split}.jsonl\0".encode())
            digest.update(path.read_bytes() if path.is_file() else b"")
            digest.update(b"\0")
    return digest.hexdigest()


def _reject_split_leaks(cases: dict[CheckName, dict[Split, list[Case]]]) -> None:
    dev = {case.id for by_split in cases.values() for case in by_split["dev"]}
    heldout = {case.id for by_split in cases.values() for case in by_split["heldout"]}
    leaked = sorted(dev & heldout)
    if leaked:
        raise DatasetError(f"case id(s) in both dev and heldout: {', '.join(leaked)}")


def _reject_duplicate_ids(cases: dict[CheckName, dict[Split, list[Case]]]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for by_split in cases.values():
        for split_cases in by_split.values():
            for case in split_cases:
                (duplicates if case.id in seen else seen).add(case.id)
    if duplicates:
        raise DatasetError(f"duplicate case id(s): {', '.join(sorted(duplicates))}")
