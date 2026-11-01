"""Convert vendored τ-bench historical trajectories into benchmark cases.

    uv run python benchmarks/converters/tau_bench.py               # regenerate the case files
    uv run python benchmarks/converters/tau_bench.py --vendor DIR  # re-trim from a tau-bench clone

The cases come from the runs listed in `tau_bench_selection.py`, read from the trimmed copies
under `benchmarks/sources/tau-bench/`. Regenerating is deterministic: the same inputs give
byte-identical case files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

# isort: split
from tau_bench_selection import CASES
from tau_bench_spec import CaseSpec
from tau_bench_trajectory import trajectory
from tau_bench_upstream import (
    BENCHMARKS_DIR,
    DATASETS_DIR,
    ORIGIN,
    SOURCE_DIR,
    UPSTREAM_TRAJECTORIES,
    Domain,
    domain_of,
    find_run,
    load_runs,
)
from tau_bench_vendor import vendor

DRAFT_PREFIX = "DRAFT label by the converter author; "

Split = Literal["dev", "validation", "heldout"]


def task_family(domain: Domain, task_id: int) -> str:
    if domain == "retail":
        return f"{ORIGIN}/retail"
    if 0 <= task_id <= 24:
        return f"{ORIGIN}/airline-0-24"
    if 25 <= task_id <= 49:
        return f"{ORIGIN}/airline-25-49"
    raise ValueError(f"airline task {task_id} is outside the pilot's task families")


SPLIT_OF_FAMILY: dict[str, Split] = {
    f"{ORIGIN}/retail": "dev",
    f"{ORIGIN}/airline-0-24": "validation",
    f"{ORIGIN}/airline-25-49": "heldout",
}


def build_case(spec: CaseSpec, source_dir: Path = SOURCE_DIR) -> tuple[Split, dict[str, object]]:
    domain = domain_of(spec.upstream_file)
    family = task_family(domain, spec.task_id)
    run = find_run(load_runs(spec.upstream_file, source_dir), spec)
    case: dict[str, object] = {
        "id": spec.id,
        "check": spec.check,
        "category": spec.category,
        "source": "community",
        "origin": ORIGIN,
        "task_family": family,
        "origin_ref": f"{UPSTREAM_TRAJECTORIES}/{spec.upstream_file}#{spec.upstream_index}",
        "label_status": "draft",
        "annotators": [],
        "trajectory": trajectory(run, spec, domain),
        "expected": spec.expected,
        "notes": DRAFT_PREFIX + spec.notes,
    }
    return SPLIT_OF_FAMILY[family], case


def case_files(source_dir: Path = SOURCE_DIR) -> dict[str, str]:
    """Every case file this converter owns, relative to the datasets folder, with its text."""
    lines: dict[str, list[str]] = {}
    for spec in sorted(CASES, key=lambda s: s.id):
        split, case = build_case(spec, source_dir)
        name = f"{spec.check}/{split}-{ORIGIN}.jsonl"
        lines.setdefault(name, []).append(json.dumps(case, ensure_ascii=False))
    return {name: "\n".join(rows) + "\n" for name, rows in sorted(lines.items())}


def write_cases(datasets_dir: Path = DATASETS_DIR, source_dir: Path = SOURCE_DIR) -> list[Path]:
    written: list[Path] = []
    for name, text in case_files(source_dir).items():
        path = datasets_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Convert vendored τ-bench runs into cases.")
    parser.add_argument("--vendor", type=Path, help="an upstream tau-bench clone to trim from")
    args = parser.parse_args(argv)
    upstream: Path | None = args.vendor
    paths = vendor(upstream) if upstream is not None else write_cases()
    for path in paths:
        print(path.relative_to(BENCHMARKS_DIR.parent))


if __name__ == "__main__":
    main()
