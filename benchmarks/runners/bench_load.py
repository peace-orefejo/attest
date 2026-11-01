"""Load and validate the benchmark datasets, and fingerprint them.

Each check folder holds one file per split, `<split>.jsonl` (the seed cases, or a private
dataset's own), plus any number of external files `<split>-<origin>.jsonl`, each holding only
cases of that origin. Every file of a split is loaded into that split. Any other entry is
rejected (see `bench_layout`).
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ValidationError

from bench_cases import CHECKS, SEED_ORIGIN, SPLITS, Case, CheckName, Split
from bench_layout import layout_problems, parse_case_file_name

DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"

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
    for path in sorted(folder.iterdir()):
        name = parse_case_file_name(path.name)
        if name is not None and name.split == split and name.origin is not None and path.is_file():
            found[name.origin] = path
    return found


def case_files(root: Path, check: CheckName, split: Split) -> list[Path]:
    """Every existing file of one check and split: its own file first, then external ones."""
    own = case_file(root, check, split)
    return [*([own] if own.is_file() else []), *external_files(root, check, split).values()]


def load_datasets(
    root: Path = DATASETS_DIR, *, allow_missing: bool = False, public: bool | None = None
) -> Datasets:
    """Load every case file under `root`, rejecting anything that breaks a dataset rule.

    Each `<split>.jsonl` must exist (an empty file is fine) unless `allow_missing`, which a
    private dataset covering only some checks uses; external `<split>-<origin>.jsonl` files are
    optional. Case ids are unique across all files, no id and no `task_family` appears in two
    splits (across every check), each case's `check` must match its folder, every case in an
    external file must have that file's origin, and any entry the loader wouldn't read is
    rejected. In the public datasets (`public`, which defaults to whether `root` is
    `DATASETS_DIR`), every case in a `<split>.jsonl` must have origin `SEED_ORIGIN`; a private
    dataset's `<split>.jsonl` may hold any origin.
    """
    if not root.is_dir():
        raise DatasetError(f"{root}: datasets folder not found")
    _reject_unknown_entries(root)
    if public is None:
        public = root.resolve() == DATASETS_DIR.resolve()
    own_origin = SEED_ORIGIN if public else None
    cases: CaseTree = {
        check: {
            split: _load_split(root, check, split, allow_missing, own_origin) for split in SPLITS
        }
        for check in CHECKS
    }
    _reject_split_leaks(cases)
    _reject_family_leaks(cases)
    _reject_duplicate_ids(cases)
    return Datasets(cases=cases, version=dataset_version(root))


def _load_split(
    root: Path, check: CheckName, split: Split, allow_missing: bool, own_origin: str | None
) -> list[Case]:
    own = case_file(root, check, split)
    cases = load_file(own, check, allow_missing=allow_missing, origin=own_origin)
    for origin, path in external_files(root, check, split).items():
        cases.extend(load_file(path, check, origin=origin))
    return cases


def load_file(
    path: Path, check: CheckName, *, allow_missing: bool = False, origin: str | None = None
) -> list[Case]:
    """Parse one JSONL case file; every error names the file and line. With `origin` (an
    external `<split>-<origin>.jsonl` file, or a public `<split>.jsonl`, which holds only seed
    cases), every case must have that origin."""
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
            raise DatasetError(f"{path}:{number}: {_origin_mismatch(path, case, origin)}")
        cases.append(case)
    return cases


def _origin_mismatch(path: Path, case: Case, origin: str) -> str:
    found = f"case {case.id!r} has origin {case.origin!r}"
    name = parse_case_file_name(path.name)
    if name is not None and name.origin is None:
        return (
            f"{found}, but a public {path.name} holds only {origin!r} cases; put external "
            f"cases in {name.split}-<origin>.jsonl"
        )
    return f"{found} but lives in the {origin!r} file"


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


def _reject_unknown_entries(root: Path) -> None:
    """An entry the loader wouldn't read is a mistake (a misspelt check, split or origin, a
    nested folder), so it is rejected rather than silently skipped."""
    problems = layout_problems(root)
    if problems:
        raise DatasetError("unrecognised entries in the datasets folder:\n" + "\n".join(problems))


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
