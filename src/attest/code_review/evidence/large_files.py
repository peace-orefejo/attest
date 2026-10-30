"""Render diffs as evidence within size limits; summarize lockfiles, omit generated files."""

from __future__ import annotations

from ...utils.diff import FileDiff, cut_hunks, parse_unified_diff
from .generated import is_generated
from .lockfiles import parser_for, summarize_lockfile
from .models import EvidenceLimits, Omission, OmissionReason, RenderedDiff

__all__ = [
    "EvidenceLimits",
    "Omission",
    "OmissionReason",
    "RenderedDiff",
    "budget_note",
    "changed_lines",
    "is_generated",
    "render_diff",
    "render_diffs",
]


def render_diffs(
    diffs: list[tuple[str, str]], limits: EvidenceLimits | None = None
) -> list[RenderedDiff]:
    """Render diffs in order, turning every diff after the run budget runs out into a note."""
    limits = limits or EvidenceLimits()
    rendered: list[RenderedDiff] = []
    used = 0
    exhausted = False
    for path, diff_text in diffs:
        item = None if exhausted else render_diff(path, diff_text, limits)
        if item is not None and used + len(item.text) > limits.max_run_chars:
            exhausted = True
            item = None
        if item is None:
            item = budget_note(path, changed_lines(path, diff_text), limits)
        else:
            used += len(item.text)
        rendered.append(item)
    return rendered


def render_diff(path: str, diff_text: str, limits: EvidenceLimits) -> RenderedDiff:
    """Render one file's diff as evidence, summarizing, omitting or cutting it as needed."""
    count = changed_lines(path, diff_text)
    if parser_for(path) is not None:
        summary = summarize_lockfile(path, diff_text)
        if summary is not None:
            return RenderedDiff(
                path=path, text=summary, omission=_omission(path, "summarized", count)
            )
    if is_generated(path, diff_text):
        return RenderedDiff(
            path=path,
            text=f"{path} (generated, {count} lines changed; diff omitted)",
            omission=_omission(path, "generated", count),
        )
    if len(diff_text) <= limits.max_file_chars:
        return RenderedDiff(path=path, text=diff_text)
    return _truncate(path, diff_text, count, limits.max_file_chars)


def changed_lines(path: str, diff_text: str) -> int:
    """Count the added and removed lines in one file's diff."""
    return sum(f.changed_line_count() for f in parse_unified_diff(diff_text, path=path))


def budget_note(path: str, count: int, limits: EvidenceLimits) -> RenderedDiff:
    """Render the omission note for a diff left out because the run budget is used up."""
    text = (
        f"{path} ({count} lines changed; diff omitted, the run evidence budget of "
        f"{limits.max_run_chars} characters is used up)"
    )
    return RenderedDiff(path=path, text=text, omission=_omission(path, "budget", count))


def _truncate(path: str, diff_text: str, count: int, max_chars: int) -> RenderedDiff:
    hunks = [h for f in parse_unified_diff(diff_text, path=path) for h in f.hunks]
    if not hunks:
        kept, _ = _cut_lines(diff_text, max_chars)
        note = f"[{path}: diff cut at {max_chars} characters; the rest was omitted]"
        return RenderedDiff(
            path=path, text=f"{kept}\n{note}", omission=_omission(path, "truncated", count)
        )
    kept, omitted = cut_hunks(FileDiff(path=path, hunks=hunks), max_chars)
    notes: list[str] = []
    if len(kept) > max_chars:
        kept, dropped = _cut_lines(kept, max_chars)
        notes.append(f"the first hunk was cut short, dropping {dropped} lines")
    if omitted:
        notes.append(f"{omitted} of {len(hunks)} hunks omitted")
    note = f"[{path}: {'; '.join(notes)}; the file diff exceeds the {max_chars} character limit]"
    return RenderedDiff(
        path=path,
        text=f"{kept}\n{note}",
        omission=_omission(path, "truncated", count, omitted),
    )


def _cut_lines(text: str, max_chars: int) -> tuple[str, int]:
    lines = text.split("\n")
    kept: list[str] = []
    used = 0
    for line in lines:
        if kept and used + len(line) + 1 > max_chars:
            break
        kept.append(line[:max_chars])
        used += len(line) + 1
    return "\n".join(kept), len(lines) - len(kept)


def _omission(path: str, reason: OmissionReason, count: int, hunks: int = 0) -> Omission:
    return Omission(path=path, reason=reason, changed_lines=count, omitted_hunks=hunks)
