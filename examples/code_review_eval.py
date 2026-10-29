"""
Score attest as a checker for an AI code-review pipeline.

Each case in tests/fixtures/code_review_cases.json is a labeled run: a flagged issue,
a diff summary, a group summary, or a canvas answer, with the diffs and files the
reviewer saw as evidence. attest checks each output against that evidence, and this
script compares attest's call with the label.

Two gate settings are scored:
  lenient  drop an output only when the evidence contradicts it
  strict   also drop it when the evidence does not mention it

    uv run python examples/code_review_eval.py
    uv run python examples/code_review_eval.py --kind issue
    uv run python examples/code_review_eval.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from attest import Attest, Severity, Trajectory
from attest.scoring.stats import wilson_interval

DEFAULT_CASES = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "code_review_cases.json"
)
KINDS = ("issue", "diff_summary", "group_summary", "canvas_answer")


def load_cases(path: Path, kind: str | None = None) -> list[dict]:
    cases = json.loads(path.read_text())["cases"]
    if kind:
        cases = [c for c in cases if c["kind"] == kind]
    for case in cases:
        case["trajectory"] = Trajectory.model_validate(case["run"])
    return cases


def outcome(report) -> tuple[str, list[str]]:
    result = report.by("faithfulness")
    findings = result.findings if result else []
    verdicts = [f.verdict for f in findings]
    if any(f.severity is Severity.FAIL for f in findings):
        return "contradicted", verdicts
    if any(f.severity is Severity.WARN for f in findings):
        return "unmentioned", verdicts
    return "supported", verdicts


def flagged(call: str, strict: bool) -> bool:
    return call == "contradicted" or (strict and call == "unmentioned")


def summarize(rows: list[dict], strict: bool) -> dict:
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_kind[row["kind"]].append(row)
    out = {}
    for kind, items in [*by_kind.items(), ("all", rows)]:
        should_flag = [r for r in items if r["expect"] == "flag"]
        should_pass = [r for r in items if r["expect"] == "pass"]
        caught = sum(flagged(r["call"], strict) for r in should_flag)
        blocked = sum(flagged(r["call"], strict) for r in should_pass)
        correct = caught + (len(should_pass) - blocked)
        out[kind] = {
            "accuracy": wilson_interval(correct, len(items)).pct(),
            "bad_outputs_caught": f"{caught}/{len(should_flag)}",
            "good_outputs_blocked": f"{blocked}/{len(should_pass)}",
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--dry-run", action="store_true", help="validate the cases without calling a model"
    )
    args = parser.parse_args()

    cases = load_cases(args.cases, args.kind)
    if args.dry_run:
        counts = defaultdict(lambda: defaultdict(int))
        for case in cases:
            counts[case["kind"]][case["expect"]] += 1
        print(f"{len(cases)} cases loaded")
        for kind, c in counts.items():
            print(f"  {kind:<14} flag={c['flag']} pass={c['pass']}")
        return

    judge_kwargs = {}
    if args.provider:
        judge_kwargs["provider"] = args.provider
    if args.model:
        judge_kwargs["model"] = args.model
    judge = Attest(**judge_kwargs)

    rows = []
    for case in cases:
        report = judge.evaluate(case["trajectory"], checks=("faithfulness",))
        call, verdicts = outcome(report)
        rows.append(
            {
                "id": case["id"],
                "kind": case["kind"],
                "expect": case["expect"],
                "call": call,
                "verdicts": verdicts,
                "lenient_ok": flagged(call, False) == (case["expect"] == "flag"),
                "strict_ok": flagged(call, True) == (case["expect"] == "flag"),
            }
        )

    summary = {"lenient": summarize(rows, False), "strict": summarize(rows, True)}
    if args.json:
        print(json.dumps({"cases": rows, "summary": summary}, indent=2))
        return

    for row in rows:
        lenient = "ok " if row["lenient_ok"] else "MISS"
        strict = "ok " if row["strict_ok"] else "MISS"
        print(
            f"{row['id']:<38} expect={row['expect']:<4} attest={row['call']:<12} "
            f"lenient {lenient}  strict {strict}  {row['verdicts']}"
        )
    for mode, table in summary.items():
        print(f"\n{mode}")
        for kind, stats in table.items():
            print(
                f"  {kind:<14} accuracy {stats['accuracy']}  caught {stats['bad_outputs_caught']}  "
                f"blocked {stats['good_outputs_blocked']}"
            )


if __name__ == "__main__":
    main()
