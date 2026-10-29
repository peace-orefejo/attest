from __future__ import annotations

from ...core import CheckResult, Finding, Report, Severity
from ..models import GateDecision, GateMode, OutputType
from ..guidelines import GUIDELINES_CHECK
from .defaults import DROPPING_VERDICTS, default_mode
from .injection import injection_findings


def _resolve_mode(output_type: OutputType, mode: GateMode | None) -> GateMode:
    resolved = default_mode(output_type)
    if mode is None:
        return resolved
    if mode not in DROPPING_VERDICTS:
        raise ValueError(f"Unknown gate mode {mode!r}. Choose from: {', '.join(DROPPING_VERDICTS)}.")
    return mode


def _faithfulness_reasons(report: Report, mode: GateMode) -> list[Finding]:
    result = report.by("faithfulness")
    if result is None:
        return []
    dropping = DROPPING_VERDICTS[mode]
    return [f for f in result.findings if f.verdict in dropping]


def _guideline_findings(report: Report) -> tuple[list[Finding], list[Finding]]:
    result = report.by(GUIDELINES_CHECK)
    if result is None:
        return [], []
    if result.metadata.get("builtin"):
        return [], [f for f in result.findings if f.severity is not Severity.PASS]
    drops = [f for f in result.findings if f.severity is Severity.FAIL]
    return drops, [f for f in result.findings if f.severity is Severity.WARN]


def gate(
    report: Report,
    output_type: OutputType,
    *,
    mode: GateMode | None = None,
    injection: CheckResult | None = None,
    paths: list[str] | None = None,
    output_index: int | None = None,
) -> GateDecision:
    """Decide whether to keep one review output.

    `reasons` lists the findings that drop it. `notes` lists findings shown beside it that do not.
    Findings against the built-in general standard are always notes; only your own rules drop.
    """
    resolved = _resolve_mode(output_type, mode)
    drops, notes = injection_findings(injection, paths, output_index)
    broken, missed = _guideline_findings(report)
    reasons = _faithfulness_reasons(report, resolved) + broken + drops
    return GateDecision(keep=not reasons, mode=resolved, reasons=reasons, notes=missed + notes)
