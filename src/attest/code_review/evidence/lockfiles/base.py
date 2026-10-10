"""Version changes parsed from a lockfile diff, the shared line walker, and the summary formatter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ....utils.diff import parse_unified_diff

Entry = tuple[str, str]
LineRule = Callable[[str], str | None]
EntryRule = Callable[[str], Entry | None]

_MIN_LABEL_WIDTH = 12
DEFAULT_MAX_ENTRIES = 40
_KIND_ORDER = {"updated": 0, "added": 1, "removed": 2}


class LockfileParseError(ValueError):
    pass


@dataclass(frozen=True)
class VersionChange:
    name: str
    old: str | None
    new: str | None

    @property
    def kind(self) -> str:
        if self.old is None:
            return "added"
        if self.new is None:
            return "removed"
        return "updated"


def collect_entries(
    diff_text: str,
    *,
    name_of: LineRule | None = None,
    version_of: LineRule | None = None,
    entry_of: EntryRule | None = None,
    shape_of: Callable[[str], bool] | None = None,
) -> tuple[list[Entry], list[Entry]]:
    """Walk a lockfile diff and return the removed and added (name, version) entries."""
    files = [f for f in parse_unified_diff(diff_text) if f.hunks]
    if not files:
        raise LockfileParseError("no hunks found")
    removed: list[Entry] = []
    added: list[Entry] = []
    recognized = changed = 0
    for file_diff in files:
        for hunk in file_diff.hunks:
            current = {"-": None, "+": None}
            for line in hunk.lines:
                text = line.text
                sides = ("-", "+") if line.kind == " " else (line.kind,)
                name = name_of(text) if name_of else None
                if name is not None:
                    for side in sides:
                        current[side] = name
                if line.kind == " ":
                    continue
                changed += 1
                bucket = removed if line.kind == "-" else added
                hit = name is not None
                entry = entry_of(text) if entry_of else None
                if entry is not None:
                    bucket.append(entry)
                    hit = True
                version = version_of(text) if version_of else None
                if version is not None:
                    hit = True
                    if current[line.kind]:
                        bucket.append((current[line.kind], version))
                if hit or (shape_of is not None and shape_of(text)):
                    recognized += 1
    if changed and not recognized:
        raise LockfileParseError("no lockfile entries recognized")
    return removed, added


def pair_changes(removed: list[Entry], added: list[Entry]) -> list[VersionChange]:
    """Pair removed and added entries by package name into version changes."""
    old = _versions_by_name(removed)
    new = _versions_by_name(added)
    changes: list[VersionChange] = []
    for name in list(dict.fromkeys([*old, *new])):
        before = [v for v in old.get(name, []) if v not in new.get(name, [])]
        after = [v for v in new.get(name, []) if v not in old.get(name, [])]
        for index in range(max(len(before), len(after))):
            changes.append(VersionChange(
                name,
                before[index] if index < len(before) else None,
                after[index] if index < len(after) else None,
            ))
    return changes


def _versions_by_name(entries: list[Entry]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for name, version in entries:
        versions = grouped.setdefault(name, [])
        if version not in versions:
            versions.append(version)
    return grouped


def format_summary(
    path: str,
    changed_lines: int,
    changes: list[VersionChange],
    *,
    max_entries: int = DEFAULT_MAX_ENTRIES,
) -> str:
    """Render version changes as the generated-lockfile summary block."""
    header = f"{path} (generated, {changed_lines} lines changed; summarized)"
    ordered = sorted(changes, key=lambda c: _KIND_ORDER[c.kind])
    if not ordered:
        return f"{header}\n  no package version changes"
    shown = ordered[:max_entries]
    labels = [c.name if c.kind == "updated" else c.kind for c in shown]
    width = max(_MIN_LABEL_WIDTH, max(len(label) for label in labels) + 2)
    old_width = max((len(c.old or "") for c in shown if c.kind == "updated"), default=0)
    lines = [header]
    for change, label in zip(shown, labels):
        if change.kind == "updated":
            body = f"{(change.old or '').ljust(old_width)} -> {change.new}"
        else:
            body = f"{change.name} {change.new or change.old}"
        lines.append(f"  {label.ljust(width)}{body}")
    if len(ordered) > len(shown):
        lines.append(f"  ... and {len(ordered) - len(shown)} more changes")
    return "\n".join(lines)


def changed_line_total(diff_text: str) -> int:
    """Count the added and removed lines across every file in a diff."""
    return sum(f.changed_line_count() for f in parse_unified_diff(diff_text))
