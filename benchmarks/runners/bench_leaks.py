"""Rules that keep the splits apart: no case id or task family in two splits, no duplicate ids.

A task family is a `/`-separated path, so `tau-bench/airline/25-49` belongs to
`tau-bench/airline`: a family and any family nested under it must share one split. Prefixes
count only at `/` boundaries, so `tau-bench/airline-0-24` and `tau-bench/airline-25-49` are
separate families.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from bench_cases import SPLITS, Case, CheckName, Split

CaseTree = dict[CheckName, dict[Split, list[Case]]]


def leak_problem(cases: CaseTree) -> str | None:
    """The first rule `cases` breaks, described, or None if it keeps the splits apart."""
    leaked = _leaks(cases, lambda case: case.id)
    if leaked:
        return f"case id(s) in more than one split: {leaked}"
    leaked = _leaks(cases, lambda case: _family(case.task_family))
    if leaked:
        return (
            f"task_family(s) in more than one split, across all checks: {leaked}; related "
            "runs must stay in one split"
        )
    nested = _nested_family_leaks(cases)
    if nested:
        return (
            f"task_family(s) nested under a family in another split: {nested}; a family and "
            "the families under it must stay in one split"
        )
    duplicates = _duplicate_ids(cases)
    if duplicates:
        return f"duplicate case id(s): {', '.join(duplicates)}"
    return None


def _splits_by(cases: CaseTree, key: Callable[[Case], str]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = defaultdict(set)
    for by_split in cases.values():
        for split, split_cases in by_split.items():
            for case in split_cases:
                found[key(case)].add(split)
    return found


def _leaks(cases: CaseTree, key: Callable[[Case], str]) -> str:
    """Each value of `key` found in more than one split, with those splits, or ''."""
    return ", ".join(
        f"{value} ({_names(splits)})"
        for value, splits in sorted(_splits_by(cases, key).items())
        if len(splits) > 1
    )


def _nested_family_leaks(cases: CaseTree) -> str:
    """Each family under another family (at a `/` boundary) that sits in a different split."""
    families = _splits_by(cases, lambda case: _family(case.task_family))
    leaks: list[str] = []
    for family, splits in sorted(families.items()):
        parts = family.split("/")
        for depth in range(1, len(parts)):
            parent = "/".join(parts[:depth])
            if parent in families and families[parent] != splits:
                leaks.append(
                    f"{family} ({_names(splits)}) under {parent} ({_names(families[parent])})"
                )
    return ", ".join(leaks)


def _family(task_family: str) -> str:
    """The family with empty path segments dropped, so `a/` and `a//b` read as `a` and `a/b`."""
    return "/".join(part for part in task_family.split("/") if part)


def _names(splits: set[str]) -> str:
    return ", ".join(split for split in SPLITS if split in splits)


def _duplicate_ids(cases: CaseTree) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for by_split in cases.values():
        for split_cases in by_split.values():
            for case in split_cases:
                (duplicates if case.id in seen else seen).add(case.id)
    return sorted(duplicates)
