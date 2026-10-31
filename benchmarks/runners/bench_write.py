"""Write confirmed cases back into their case files, leaving every other line untouched."""

from __future__ import annotations

import json
from pathlib import Path

from bench_cases import CHECKS, SPLITS, Case
from bench_load import case_file


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
