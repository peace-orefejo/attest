from __future__ import annotations

from ...results import CheckResult, Finding, Report
from ..models import INJECTION_VERDICTS, GateDecision, GateMode, OutputType
from .defaults import DROPPING_VERDICTS, default_mode

INJECTION_CHECK = "code_injection"
BLOCKING_INJECTION = frozenset({"payload", "compromised"})


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


def _applies(finding: Finding, paths: list[str] | None) -> bool:
    if paths is None:
        return True
    file = finding.metadata.get("file")
    return file is None or file in paths


def _injection_findings(injection: CheckResult | None, paths: list[str] | None) -> list[Finding]:
    if injection is None:
        return []
    if injection.check != INJECTION_CHECK:
        raise ValueError(f"Expected a {INJECTION_CHECK!r} result, got {injection.check!r}.")
    return [
        f for f in injection.findings
        if f.verdict in INJECTION_VERDICTS and f.verdict != "clean" and _applies(f, paths)
    ]


def gate(
    report: Report,
    output_type: OutputType,
    *,
    mode: GateMode | None = None,
    injection: CheckResult | None = None,
    paths: list[str] | None = None,
) -> GateDecision:
    """Decide whether to keep one review output given its report and injection verdicts."""
    resolved = _resolve_mode(output_type, mode)
    reasons = _faithfulness_reasons(report, resolved)
    flagged = _injection_findings(injection, paths)
    blocked = any(f.verdict in BLOCKING_INJECTION for f in flagged)
    return GateDecision(keep=not reasons and not blocked, mode=resolved, reasons=reasons + flagged)
