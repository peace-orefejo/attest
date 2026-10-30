"""What each code_injection finding means for one review output: drop, note or ignore."""

from __future__ import annotations

from typing import Literal, cast

from ...results import CheckResult, Finding
from ..injection.segments import PR_FILE
from ..models import INJECTION_VERDICTS
from .split import FindingSplit

INJECTION_CHECK = "code_injection"
BLOCKING_INJECTION = frozenset({"payload", "compromised"})

Action = Literal["drop", "note", "ignore"]


def injection_findings(
    injection: CheckResult | None,
    paths: list[str] | None,
    output_index: int | None,
) -> FindingSplit:
    """Injection findings that drop one output, and those shown beside it as notes."""
    split = FindingSplit()
    if injection is None:
        return split
    if injection.check != INJECTION_CHECK:
        raise ValueError(f"Expected a {INJECTION_CHECK!r} result, got {injection.check!r}.")
    for finding in injection.findings:
        action = _action(finding, paths, output_index)
        if action == "drop":
            split.drops.append(finding)
        elif action == "note":
            split.notes.append(finding)
    return split


def _action(finding: Finding, paths: list[str] | None, output_index: int | None) -> Action:
    if finding.verdict not in INJECTION_VERDICTS or finding.verdict == "clean":
        return "ignore"
    affected = _affected_outputs(finding)
    if finding.verdict == "compromised" and affected and output_index is not None:
        if output_index in affected:
            return "drop"
        return "note" if _in_paths(finding, paths) else "ignore"
    if not _in_paths(finding, paths):
        return "ignore"
    return "drop" if finding.verdict in BLOCKING_INJECTION else "note"


def _in_paths(finding: Finding, paths: list[str] | None) -> bool:
    if paths is None:
        return True
    file = finding.metadata.get("file")
    return file is None or file == PR_FILE or file in paths


def _affected_outputs(finding: Finding) -> list[int]:
    value = finding.metadata.get("affected_outputs")
    if not isinstance(value, list):
        return []
    items = cast("list[object]", value)
    return [item for item in items if isinstance(item, int) and not isinstance(item, bool)]
