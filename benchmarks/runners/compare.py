"""Compare two benchmark reports and fail on a regression.

    uv run python benchmarks/runners/compare.py old.json new.json
    uv run python benchmarks/runners/compare.py old.json new.json --tolerance 0.05

Refuses (exit 2, no metric deltas) when the reports aren't like for like: different dataset
versions, splits, settings, provider or model, or either report has cases that errored or
didn't run, ran out of budget, or has a check below --min-coverage. --allow-model-change lets
a model change through; --allow-incompatible forces any comparison and says what it bypassed.

Otherwise prints metric deltas per check (and per origin, for a check that mixes origins) and
the cases whose correctness flipped, and exits 1 when F1 or recall in any binary view drops by
more than the tolerance: for a check as a whole, or for one of its origins with at least
`bench_compare.MIN_ORIGIN_CASES` cases in both reports.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bench_compare import compare
from bench_compare_format import format_comparison, format_refusal
from bench_compat import incompatibilities
from bench_report import DEFAULT_MIN_COVERAGE, FORMAT_VERSION, BenchmarkReport

DEFAULT_TOLERANCE = 0.02
REFUSED = 2


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
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=DEFAULT_MIN_COVERAGE,
        help=f"refuse a report with a check below this coverage (default {DEFAULT_MIN_COVERAGE})",
    )
    parser.add_argument(
        "--allow-model-change", action="store_true", help="compare runs on different models"
    )
    parser.add_argument(
        "--allow-incompatible",
        action="store_true",
        help="compare even when the reports aren't like for like; the output lists what failed",
    )
    parser.add_argument("--json", action="store_true", help="print the comparison as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        old, new = _load(args.old), _load(args.new)
    except (OSError, ValueError) as exc:
        print(f"can't read report: {exc}", file=sys.stderr)
        return REFUSED
    problems = incompatibilities(
        old, new, min_coverage=args.min_coverage, allow_model_change=args.allow_model_change
    )
    if problems and not args.allow_incompatible:
        print(format_refusal(problems), end="", file=sys.stderr)
        return REFUSED
    comparison = compare(old, new, tolerance=args.tolerance, bypassed=problems)
    if args.json:
        print(comparison.model_dump_json(indent=2))
    else:
        print(format_comparison(comparison), end="")
    return 1 if comparison.regressed else 0


def _load(path: Path) -> BenchmarkReport:
    report = BenchmarkReport.model_validate_json(path.read_text(encoding="utf-8"))
    if report.format_version != FORMAT_VERSION:
        raise ValueError(f"{path}: format_version {report.format_version}, need {FORMAT_VERSION}")
    return report


if __name__ == "__main__":
    raise SystemExit(main())
