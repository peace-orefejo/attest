"""Run the attest benchmark on one split and write a JSON report.

    uv run python benchmarks/runners/run.py --check faithfulness --split dev \\
        --provider anthropic --out benchmarks/reports/faithfulness-dev.json
    uv run python benchmarks/runners/run.py --offline          # no key: tool use + injection scan
    uv run python benchmarks/runners/run.py --offline --split validation
    uv run python benchmarks/runners/run.py --split heldout --heldout --out ...

The splits are dev (tuning), validation (checking a change before release) and heldout. The
held-out split is refused unless --heldout is passed too, so it isn't used by accident
while developing. A Markdown summary is printed to stdout.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from attest import Attest, Budget
from bench_cases import CHECKS, SPLITS, CheckName
from bench_check_metrics import Prices
from bench_grade import OFFLINE_CHECKS, GradeSettings
from bench_load import DATASETS_DIR, DatasetError, load_datasets
from bench_private import ID_KEY_ENV, id_key_from_env, key_fingerprint, withhold_case_details
from bench_report import DEFAULT_MIN_COVERAGE
from bench_run import run_benchmark
from bench_summary import markdown_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check",
        action="append",
        choices=[*CHECKS, "all"],
        help="check to run; repeat for several (default: all)",
    )
    parser.add_argument("--split", choices=SPLITS, default="dev")
    parser.add_argument(
        "--heldout", action="store_true", help="confirm you mean to run the held-out split"
    )
    parser.add_argument("--provider", default="anthropic")
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-calls", type=int, default=None, help="stop after N model calls")
    parser.add_argument("--cache-dir", type=Path, default=None, help="cache model responses here")
    parser.add_argument(
        "--offline", action="store_true", help="run only what needs no model (no API key)"
    )
    parser.add_argument(
        "--appropriate", action="store_true", help="tool_use: also run the tool-choice check"
    )
    parser.add_argument("--answer-kind", default="factual", help="faithfulness answer kind")
    parser.add_argument("--price-per-mtok-in", type=float, default=None)
    parser.add_argument("--price-per-mtok-out", type=float, default=None)
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=DEFAULT_MIN_COVERAGE,
        help="share of cases per check that must be graded for a publishable report "
        f"(default {DEFAULT_MIN_COVERAGE})",
    )
    parser.add_argument(
        "--datasets",
        type=Path,
        default=DATASETS_DIR,
        help="folder of case files (default: the public benchmarks/datasets). Any other folder "
        "is treated as private: it may cover only some checks, and the report withholds case "
        "contents",
    )
    parser.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.split == "heldout" and not args.heldout:
        parser.error("--split heldout also needs --heldout; keep held-out out of development")
    if not 0.0 <= args.min_coverage <= 1.0:
        parser.error("--min-coverage must be between 0 and 1")
    checks = _selected_checks(args.check)
    if args.offline and args.check and "all" not in args.check:
        needs_model = [c for c in checks if c not in OFFLINE_CHECKS]
        if needs_model:
            parser.error(f"{', '.join(needs_model)} needs a model; drop --offline")
    private = args.datasets.resolve() != DATASETS_DIR.resolve()
    try:
        datasets = load_datasets(args.datasets, allow_missing=private)
    except DatasetError as exc:
        print(f"dataset error: {exc}", file=sys.stderr)
        return 2

    report = run_benchmark(
        _judge(args),
        datasets,
        checks=checks,
        split=args.split,
        settings=GradeSettings(
            offline=args.offline, answer_kind=args.answer_kind, appropriate=args.appropriate
        ),
        prices=Prices(input=args.price_per_mtok_in, output=args.price_per_mtok_out),
        min_coverage=args.min_coverage,
    )
    if private:
        key = id_key_from_env()
        if key is None:
            print(
                f"warning: {ID_KEY_ENV} is not set, so private case ids are plain hashes that "
                "anyone who can guess an id can confirm",
                file=sys.stderr,
            )
        report = report.model_copy(
            update={
                "dataset_visibility": "private",
                "case_id_key": key_fingerprint(key),
                "cases": withhold_case_details(report.cases, key),
            }
        )
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(markdown_summary(report), end="")
    return 0


def _selected_checks(chosen: list[str] | None) -> list[CheckName]:
    if not chosen or "all" in chosen:
        return list(CHECKS)
    return [check for check in CHECKS if check in chosen]


def _judge(args: argparse.Namespace) -> Attest:
    budget = Budget(max_calls=args.max_calls) if args.max_calls is not None else None
    cache = str(args.cache_dir) if args.cache_dir is not None else False
    return Attest(provider=args.provider, model=args.model, cache=cache, budget=budget)


if __name__ == "__main__":
    raise SystemExit(main())
