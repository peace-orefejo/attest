from __future__ import annotations

from ...results import CheckResult, Finding, Report
from ..models import GateDecision, GateMode, OutputType
from .defaults import DROPPING_VERDICTS, default_mode
from .injection import injection_reasons


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


def gate(
    report: Report,
    output_type: OutputType,
    *,
    mode: GateMode | None = None,
    injection: CheckResult | None = None,
    paths: list[str] | None = None,
    output_index: int | None = None,
) -> GateDecision:
    """Decide whether to keep one review output given its report and injection verdicts."""
    resolved = _resolve_mode(output_type, mode)
    reasons = _faithfulness_reasons(report, resolved)
    flagged, blocked = injection_reasons(injection, paths, output_index)
    return GateDecision(keep=not reasons and not blocked, mode=resolved, reasons=reasons + flagged)
