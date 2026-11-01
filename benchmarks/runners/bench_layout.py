"""The file layout of a datasets folder: which names the loader reads and which it rejects.

A datasets folder holds one folder per check and, optionally, a top-level `README.md`. A check
folder holds only case files named exactly `<split>.jsonl` or `<split>-<origin>.jsonl`, where
the origin isn't itself a split name. Hidden entries (names starting with `.`, such as
`.DS_Store`, `.gitkeep` or a private folder's `.git`) are ignored everywhere. Anything else
would be skipped silently, so it is reported as a mistake instead.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from bench_cases import CHECKS, SPLITS, Split

ROOT_FILES = frozenset({"README.md"})
"""Files allowed at the top of a datasets folder, beside the check folders."""

_NAME = re.compile(r"(?P<split>[a-z]+)(?:-(?P<origin>[a-z0-9][a-z0-9_-]*))?\.jsonl")


class CaseFileName(BaseModel):
    """A parsed case file name: the split's own file when `origin` is None."""

    split: Split
    origin: str | None = None


def parse_case_file_name(name: str) -> CaseFileName | None:
    """The split and origin a case file name stands for, or None if the loader won't read it.

    Matching is case-sensitive: `dev.JSONL` and `Dev.jsonl` are not case files."""
    match = _NAME.fullmatch(name)
    if match is None:
        return None
    split, origin = match["split"], match["origin"]
    if split not in SPLITS or origin in SPLITS:
        return None
    return CaseFileName.model_validate({"split": split, "origin": origin})


def layout_problems(root: Path) -> list[str]:
    """Every entry under `root` the loader wouldn't read, each as a one-line problem."""
    problems: list[str] = []
    for entry in _visible(root):
        if entry.is_dir() and entry.name in CHECKS:
            problems.extend(_check_folder_problems(entry))
        elif entry.is_dir():
            problems.append(f"{entry}: unknown folder; check folders are named {', '.join(CHECKS)}")
        elif entry.name not in ROOT_FILES:
            problems.append(
                f"{entry}: unknown file; only check folders and {', '.join(sorted(ROOT_FILES))} "
                "belong at the top of a datasets folder"
            )
    return problems


def _check_folder_problems(folder: Path) -> list[str]:
    problems: list[str] = []
    for entry in _visible(folder):
        if entry.is_dir():
            problems.append(f"{entry}: subfolders aren't read; put case files in {folder}")
        elif parse_case_file_name(entry.name) is None:
            problems.append(
                f"{entry}: unrecognised case file; name it <split>.jsonl or "
                f"<split>-<origin>.jsonl, with split one of {', '.join(SPLITS)} and an origin "
                "that isn't a split name"
            )
    return problems


def _visible(folder: Path) -> list[Path]:
    return sorted(path for path in folder.iterdir() if not path.name.startswith("."))
