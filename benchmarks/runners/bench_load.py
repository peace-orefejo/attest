"""Load and validate the benchmark datasets, and fingerprint them.

Each check folder holds one file per split, `<split>.jsonl` (the seed cases, or a private
dataset's own), plus any number of external files `<split>-<origin>.jsonl`, each holding only
cases of that origin. Every file of a split is loaded into that split.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ValidationError

from bench_cases import CHECKS, SPLITS, Case, CheckName, Split

DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"
_EXTERNAL = re.compile(r"(?P<split>[a-z]+)-(?P<origin>[a-z0-9][a-z0-9_-]*)\.jsonl")

CaseTree = dict[CheckName, dict[Split, list[Case]]]


class DatasetError(ValueError):
    """A case file is malformed or the datasets break a rule (duplicates, split leaks)."""


class Datasets(BaseModel):
    """Every case of every check and split, validated together."""

    cases: CaseTree
    version: str

    def split(self, check: CheckName, split: Split) -> list[Case]:
        return self.cases[check][split]


def case_file(root: Path, check: CheckName, split: Split) -> Path:
    """The split's own file: the seed cases, or a private dataset's cases."""
    return root / check / f"{split}.jsonl"


def external_files(root: Path, check: CheckName, split: Split) -> dict[str, Path]:
    """The split's external files, `<split>-<origin>.jsonl`, keyed by origin in name order."""
    folder = root / check
    if not folder.is_dir():
        return {}
    found: dict[str, Path] = {}
    for path in sorted(folder.glob(f"{split}-*.jsonl")):
        match = _EXTERNAL.fullmatch(path.name)
        if match is not None and match["split"] == split:
            found[match["origin"]] = path
    return found


def case_files(root: Path, check: CheckName, split: Split) -> list[Path]:
    """Every existing file of one check and split: its own file first, then external ones."""
    own = case_file(root, check, split)
    return [*([own] if own.is_file() else []), *external_files(root, check, split).values()]


def load_datasets(root: Path = DATASETS_DIR, *, allow_missing: bool = False) -> Datasets:
    """Load every case file under `root`, rejecting anything that breaks a dataset rule.

    Each `<split>.jsonl` must exist (an empty file is fine) unless `allow_missing`, which a
    private dataset covering only some checks uses; external `<split>-<origin>.jsonl` files are
    optional. Case ids are unique across all files, no id and no `task_family` appears in two
    splits (across every check), each case's `check` must match its folder, every case in an
    external file must have that file's origin, and any other `.jsonl` file is rejected.
    """
    if not root.is_dir():
        raise DatasetError(f"{root}: datasets folder not found")
    for check in CHECKS:
        _reject_unknown_files(root, check)
    cases: CaseTree = {
        check: {split: _load_split(root, check, split, allow_missing) for split in SPLITS}
        for check in CHECKS
    }
    _reject_split_leaks(cases)
    _reject_family_leaks(cases)
    _reject_duplicate_ids(cases)
    return Datasets(cases=cases, version=dataset_version(root))


def _load_split(root: Path, check: CheckName, split: Split, allow_missing: bool) -> list[Case]:
    cases = load_file(case_file(root, check, split), check, allow_missing=allow_missing)
    for origin, path in external_files(root, check, split).items():
        cases.extend(load_file(path, check, origin=origin))
    return cases


def load_file(
    path: Path, check: CheckName, *, allow_missing: bool = False, origin: str | None = None
) -> list[Case]:
    """Parse one JSONL case file; every error names the file and line. With `origin` (an
    external `<split>-<origin>.jsonl` file), every case must have that origin."""
    if not path.is_file():
        if allow_missing:
            return []
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
        if origin is not None and case.origin != origin:
            raise DatasetError(
                f"{path}:{number}: case {case.id!r} has origin {case.origin!r} "
                f"but lives in the {origin!r} file"
            )
        cases.append(case)
    return cases


def dataset_version(root: Path = DATASETS_DIR) -> str:
    """SHA-256 over every case file's path and bytes, external files included, so any edit,
    added file or removed file changes the version."""
    digest = hashlib.sha256()
    for check in CHECKS:
        for split in SPLITS:
            path = case_file(root, check, split)
            digest.update(f"{check}/{split}.jsonl\0".encode())
            digest.update(path.read_bytes() if path.is_file() else b"")
            digest.update(b"\0")
            for external in external_files(root, check, split).values():
                digest.update(f"{check}/{external.name}\0".encode())
                digest.update(external.read_bytes())
                digest.update(b"\0")
    return digest.hexdigest()


def _reject_unknown_files(root: Path, check: CheckName) -> None:
    """A `.jsonl` file the loader wouldn't read is a mistake (a misspelt split or origin), so
    it is rejected rather than silently skipped."""
    folder = root / check
    if not folder.is_dir():
        return
    known = {f"{split}.jsonl" for split in SPLITS} | {
        path.name for split in SPLITS for path in external_files(root, check, split).values()
    }
    unknown = sorted(path.name for path in folder.glob("*.jsonl") if path.name not in known)
    if unknown:
        raise DatasetError(
            f"{folder}: unrecognised case file(s) {', '.join(unknown)}; name them "
            f"<split>.jsonl or <split>-<origin>.jsonl, with split one of {', '.join(SPLITS)}"
        )


def _leaks(cases: CaseTree, key: Callable[[Case], str]) -> str:
    """Each value of `key` found in more than one split, with those splits, or ''."""
    found: dict[str, set[str]] = defaultdict(set)
    for by_split in cases.values():
        for split, split_cases in by_split.items():
            for case in split_cases:
                found[key(case)].add(split)
    return ", ".join(
        f"{value} ({', '.join(split for split in SPLITS if split in splits)})"
        for value, splits in sorted(found.items())
        if len(splits) > 1
    )


def _reject_split_leaks(cases: CaseTree) -> None:
    leaked = _leaks(cases, lambda case: case.id)
    if leaked:
        raise DatasetError(f"case id(s) in more than one split: {leaked}")


def _reject_family_leaks(cases: CaseTree) -> None:
    leaked = _leaks(cases, lambda case: case.task_family)
    if leaked:
        raise DatasetError(
            f"task_family(s) in more than one split, across all checks: {leaked}; related "
            "runs must stay in one split"
        )


def _reject_duplicate_ids(cases: CaseTree) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for by_split in cases.values():
        for split_cases in by_split.values():
            for case in split_cases:
                (duplicates if case.id in seen else seen).add(case.id)
    if duplicates:
        raise DatasetError(f"duplicate case id(s): {', '.join(sorted(duplicates))}")
