"""Scoring and formatting helpers for examples/code_review_eval.py."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from attest import Report, Trajectory
from attest.code_review.gate import gate
from attest.code_review.models import OUTPUT_TYPES
from attest.scoring.stats import wilson_interval

MODES = ("lenient", "strict")


def load_cases(path: Path, kind: str | None = None) -> list[dict]:
    """Load labeled cases, optionally keeping one kind, with each run parsed."""
    cases = json.loads(path.read_text())["cases"]
    if kind:
        cases = [c for c in cases if c["kind"] == kind]
    for case in cases:
        if case["kind"] not in OUTPUT_TYPES:
            raise ValueError(f"Case {case['id']!r} has unknown kind {case['kind']!r}.")
        case["trajectory"] = Trajectory.model_validate(case["run"])
    return cases


def score_case(case: dict, report: Report) -> dict:
    """Gate one case's report in both modes and compare each call with its label."""
    result = report.by("faithfulness")
    row = {
        "id": case["id"],
        "kind": case["kind"],
        "expect": case["expect"],
        "verdicts": [f.verdict for f in result.findings] if result else [],
    }
    should_drop = case["expect"] == "flag"
    for mode in MODES:
        decision = gate(report, case["kind"], mode=mode)
        row[f"{mode}_drop"] = not decision.keep
        row[f"{mode}_ok"] = (not decision.keep) == should_drop
        row[f"{mode}_reasons"] = [f.subject for f in decision.reasons]
    return row


def summarize(rows: list[dict], mode: str) -> dict:
    """Accuracy with a Wilson interval plus caught and blocked counts, per kind and overall."""
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_kind[row["kind"]].append(row)
    out = {}
    for kind, items in [*list(by_kind.items()), ("all", rows)]:
        should_flag = [r for r in items if r["expect"] == "flag"]
        should_pass = [r for r in items if r["expect"] == "pass"]
        caught = sum(r[f"{mode}_drop"] for r in should_flag)
        blocked = sum(r[f"{mode}_drop"] for r in should_pass)
        correct = caught + (len(should_pass) - blocked)
        out[kind] = {
            "accuracy": wilson_interval(correct, len(items)).pct(),
            "bad_outputs_caught": f"{caught}/{len(should_flag)}",
            "good_outputs_blocked": f"{blocked}/{len(should_pass)}",
        }
    return out


def summarize_modes(rows: list[dict]) -> dict:
    """Summaries for every gate mode."""
    return {mode: summarize(rows, mode) for mode in MODES}


def _mark(row: dict, mode: str) -> str:
    return "ok  " if row[f"{mode}_ok"] else "MISS"


def _stats(stats: dict) -> str:
    return (
        f"accuracy {stats['accuracy']}  caught {stats['bad_outputs_caught']}  "
        f"blocked {stats['good_outputs_blocked']}"
    )


def format_single(rows: list[dict], summary: dict) -> list[str]:
    """Per-case lines followed by the per-mode summary for one answer kind."""
    lines = [
        f"{r['id']:<38} expect={r['expect']:<4} lenient {_mark(r, 'lenient')}  "
        f"strict {_mark(r, 'strict')}  {r['verdicts']}"
        for r in rows
    ]
    for mode, table in summary.items():
        lines.append(f"\n{mode}")
        lines.extend(f"  {kind:<14} {_stats(stats)}" for kind, stats in table.items())
    return lines


def format_compare(results: dict[str, list[dict]]) -> list[str]:
    """Answer kinds side by side: one column pair per kind, then summaries grouped by case kind."""
    kinds = list(results)
    header = f"{'case':<38} {'expect':<6} " + "  ".join(f"{k + ' L/S':<11}" for k in kinds)
    lines = [header]
    first = results[kinds[0]]
    for i, row in enumerate(first):
        cells = "  ".join(
            f"{_mark(results[k][i], 'lenient')}/{_mark(results[k][i], 'strict'):<6}" for k in kinds
        )
        lines.append(f"{row['id']:<38} {row['expect']:<6} {cells}")
    summaries = {k: summarize_modes(rows) for k, rows in results.items()}
    for mode in MODES:
        lines.append(f"\n{mode}")
        for case_kind in summaries[kinds[0]][mode]:
            for j, k in enumerate(kinds):
                label = case_kind if j == 0 else ""
                lines.append(f"  {label:<14} {k:<8} {_stats(summaries[k][mode][case_kind])}")
    return lines


def dry_run_lines(cases: list[dict], answer_kinds: list[str]) -> list[str]:
    """Case counts per kind and label, without calling a model."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for case in cases:
        counts[case["kind"]][case["expect"]] += 1
    lines = [f"{len(cases)} cases loaded, answer kinds: {', '.join(answer_kinds)}"]
    lines.extend(f"  {kind:<14} flag={c['flag']} pass={c['pass']}" for kind, c in counts.items())
    return lines
