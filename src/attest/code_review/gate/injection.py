"""What each code_injection finding means for one review output: drop, note or ignore."""

from __future__ import annotations

from typing import Literal

from ...results import CheckResult, Finding
from ..models import INJECTION_VERDICTS

INJECTION_CHECK = "code_injection"
BLOCKING_INJECTION = frozenset({"payload", "compromised"})

Action = Literal["drop", "note", "ignore"]


def _in_paths(finding: Finding, paths: list[str] | None) -> bool:
    if paths is None:
        return True
    file = finding.metadata.get("file")
    return file is None or file in paths


def _action(finding: Finding, paths: list[str] | None, output_index: int | None) -> Action:
    if finding.verdict not in INJECTION_VERDICTS or finding.verdict == "clean":
        return "ignore"
    affected = finding.metadata.get("affected_outputs")
    if finding.verdict == "compromised" and affected and output_index is not None:
        if output_index in affected:
            return "drop"
        return "note" if _in_paths(finding, paths) else "ignore"
    if not _in_paths(finding, paths):
        return "ignore"
    return "drop" if finding.verdict in BLOCKING_INJECTION else "note"


def injection_reasons(
    injection: CheckResult | None,
    paths: list[str] | None,
    output_index: int | None,
) -> tuple[list[Finding], bool]:
    """Injection findings that apply to one output, and whether any of them drops it."""
    if injection is None:
        return [], False
    if injection.check != INJECTION_CHECK:
        raise ValueError(f"Expected a {INJECTION_CHECK!r} result, got {injection.check!r}.")
    reasons: list[Finding] = []
    blocked = False
    for finding in injection.findings:
        action = _action(finding, paths, output_index)
        if action == "ignore":
            continue
        reasons.append(finding)
        blocked = blocked or action == "drop"
    return reasons, blocked
