"""Re-trim the vendored inputs from a tau-bench clone: only the selected runs, labels dropped."""

from __future__ import annotations

import json
from pathlib import Path

# isort: split
from tau_bench_selection import CASES
from tau_bench_upstream import SOURCE_DIR, UPSTREAM_TRAJECTORIES


def selected_indices(entries: list[dict[str, object]], upstream_file: str) -> list[int]:
    """The upstream positions of the selected runs, checked against their task and trial."""
    indices: set[int] = set()
    for spec in CASES:
        if spec.upstream_file != upstream_file:
            continue
        entry = entries[spec.upstream_index]
        if (entry["task_id"], entry["trial"]) != (spec.task_id, spec.trial):
            raise ValueError(f"{spec.id}: upstream index {spec.upstream_index} is another run")
        indices.add(spec.upstream_index)
    return sorted(indices)


def vendor(upstream_dir: Path, source_dir: Path = SOURCE_DIR) -> list[Path]:
    """Copy only the selected runs from an upstream clone, dropping `reward` and `info`."""
    written: list[Path] = []
    for upstream_file in sorted({spec.upstream_file for spec in CASES}):
        path = upstream_dir / UPSTREAM_TRAJECTORIES / upstream_file
        entries: list[dict[str, object]] = json.loads(path.read_text(encoding="utf-8"))
        kept = [
            {key: entries[index][key] for key in ("task_id", "trial", "traj")}
            for index in selected_indices(entries, upstream_file)
        ]
        target = source_dir / UPSTREAM_TRAJECTORIES / upstream_file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")
        written.append(target)
    return written
