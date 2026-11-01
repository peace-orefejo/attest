"""Markdown for compare.py: the comparison, or why it was refused."""

from __future__ import annotations

from bench_compare import Comparison, Deltas


def format_comparison(comparison: Comparison) -> str:
    lines = _bypass_banner(comparison.bypassed)
    for check, metrics in comparison.deltas.items():
        lines.append(f"## {check}")
        lines.append("| metric | old | new | delta |")
        lines.append("|---|---|---|---|")
        lines.extend(f"| {row}" for row in _rows(metrics))
        lines.append("")
        by_origin = comparison.origin_deltas.get(check)
        if by_origin:
            lines.append(f"### {check} by origin")
            lines.append("| origin | metric | old | new | delta |")
            lines.append("|---|---|---|---|---|")
            for origin, deltas in by_origin.items():
                lines.extend(f"| {origin} | {row}" for row in _rows(deltas))
            lines.append("")
    if comparison.flips:
        lines.append("## Flipped cases")
        lines.extend(
            f"- {f.check} {f.id}: {_mark(f.old_correct)} -> {_mark(f.new_correct)}"
            for f in comparison.flips
        )
        lines.append("")
    lines.extend(f"- warning: {note}" for note in comparison.warnings)
    lines.extend(f"- REGRESSION: {note}" for note in comparison.regressions)
    if not comparison.regressions:
        lines.append("No regressions beyond the tolerance.")
    return "\n".join(lines).rstrip() + "\n"


def format_refusal(reasons: list[str]) -> str:
    """Why compare refused, with no metric deltas."""
    lines = ["Refusing to compare: the reports are not like for like.", ""]
    lines.extend(f"- {reason}" for reason in reasons)
    lines.append("")
    lines.append("Fix the runs, or pass --allow-incompatible to compare them anyway.")
    return "\n".join(lines) + "\n"


def _rows(deltas: Deltas) -> list[str]:
    """Each metric as the cells after a row's leading `| `: name, old, new, delta."""
    return [
        f"{name} | {_num(d.old)} | {_num(d.new)} | {_signed(d.delta)} |"
        for name, d in deltas.items()
    ]


def _bypass_banner(bypassed: list[str]) -> list[str]:
    if not bypassed:
        return []
    return [
        "!!! FORCED COMPARISON (--allow-incompatible): these reports are NOT like for like. "
        "Bypassed checks:",
        *(f"!!! - {reason}" for reason in bypassed),
        "",
    ]


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _signed(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.3f}"


def _mark(correct: bool) -> str:
    return "correct" if correct else "wrong"
