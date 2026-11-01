"""Write confirmed cases back into their case files, leaving every other line untouched."""

from __future__ import annotations

import json
from pathlib import Path

from bench_cases import CHECKS, SPLITS, Case
from bench_load import case_files


def write_cases(root: Path, confirmed: dict[str, Case]) -> int:
    """Replace each confirmed case's line in whichever case file holds it, external files
    included; returns how many were written."""
    written = 0
    for check in CHECKS:
        for split in SPLITS:
            for path in case_files(root, check, split):
                written += _rewrite(path, confirmed)
    return written


def _rewrite(path: Path, confirmed: dict[str, Case]) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    written = 0
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        case_id = json.loads(line)["id"]
        if case_id in confirmed:
            lines[index] = json.dumps(
                confirmed[case_id].model_dump(mode="json", exclude_unset=True),
                ensure_ascii=False,
            )
            written += 1
    if written:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return written
