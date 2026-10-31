"""Compare two benchmark reports and fail on a regression.

    uv run python benchmarks/runners/compare.py old.json new.json
    uv run python benchmarks/runners/compare.py old.json new.json --tolerance 0.05

Prints metric deltas per check and the cases whose correctness flipped. Exits 1 when any
check's violation-detection F1 or recall drops by more than the tolerance.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bench_compare import compare, format_comparison
from bench_report import BenchmarkReport

DEFAULT_TOLERANCE = 0.02


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("old", type=Path)
    parser.add_argument("new", type=Path)
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help=f"largest allowed drop in F1 or recall (default {DEFAULT_TOLERANCE})",
    )
    parser.add_argument("--json", action="store_true", help="print the comparison as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    old = _load(args.old)
    new = _load(args.new)
    comparison = compare(old, new, tolerance=args.tolerance)
    if args.json:
        print(comparison.model_dump_json(indent=2))
    else:
        print(format_comparison(comparison), end="")
    return 1 if comparison.regressed else 0


def _load(path: Path) -> BenchmarkReport:
    return BenchmarkReport.model_validate_json(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
