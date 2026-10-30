"""
Score attest as a checker for an AI code-review pipeline.

Each case in tests/fixtures/code_review_cases.json is a labeled run: a flagged issue,
a diff summary, a group summary, or a canvas answer, with the diffs and files the
reviewer saw as evidence. attest checks each output against that evidence, and this
script passes the report through attest.code_review.gate and compares the call with
the label. Each case's kind is its output type.

Two gate settings are scored:
  lenient  drop an output only when the evidence contradicts it
  strict   also drop it when the evidence does not mention it

    uv run python examples/code_review_eval.py
    uv run python examples/code_review_eval.py --kind issue
    uv run python examples/code_review_eval.py --answer-kind factual
    uv run python examples/code_review_eval.py --compare
    uv run python examples/code_review_eval.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from code_review_eval_report import (
    dry_run_lines,
    format_compare,
    format_single,
    load_cases,
    score_case,
    summarize_modes,
)

from attest import Attest
from attest.code_review.models import OUTPUT_TYPES

DEFAULT_CASES = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "attest"
    / "code_review"
    / "fixtures"
    / "code_review_cases.json"
)
ANSWER_KINDS = ("factual", "plan", "code", "auto")
COMPARE_KINDS = ("factual", "code")


def run_cases(judge: Attest, cases: list[dict], answer_kind: str) -> list[dict]:
    """Evaluate every case's faithfulness with one answer kind and score it."""
    return [
        score_case(
            case,
            judge.evaluate(case["trajectory"], checks=("faithfulness",), answer_kind=answer_kind),
        )
        for case in cases
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--kind", choices=OUTPUT_TYPES)
    parser.add_argument("--answer-kind", choices=ANSWER_KINDS, default="code")
    parser.add_argument(
        "--compare",
        action="store_true",
        help=f"run {' and '.join(COMPARE_KINDS)} on the same cases and print them side by side",
    )
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--dry-run", action="store_true", help="validate the cases without calling a model"
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    answer_kinds = list(COMPARE_KINDS) if args.compare else [args.answer_kind]
    cases = load_cases(args.cases, args.kind)
    if args.dry_run:
        print("\n".join(dry_run_lines(cases, answer_kinds)))
        return

    judge_kwargs = {k: v for k, v in (("provider", args.provider), ("model", args.model)) if v}
    judge = Attest(**judge_kwargs)
    results = {kind: run_cases(judge, cases, kind) for kind in answer_kinds}

    if args.json:
        payload = {
            kind: {"cases": rows, "summary": summarize_modes(rows)}
            for kind, rows in results.items()
        }
        print(json.dumps(payload, indent=2))
        return
    if args.compare:
        print("\n".join(format_compare(results)))
        return
    rows = results[args.answer_kind]
    print("\n".join(format_single(rows, summarize_modes(rows))))


if __name__ == "__main__":
    main()
