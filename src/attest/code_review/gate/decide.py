from __future__ import annotations

from ...results import CheckResult, Finding, Report, Severity
from ..guidelines import GUIDELINES_CHECK
from ..models import GateDecision, GateMode, OutputType
from .defaults import DROPPING_VERDICTS, default_mode
from .injection import injection_findings
from .split import FindingSplit


def gate(
    report: Report,
    output_type: OutputType | str,
    *,
    mode: GateMode | str | None = None,
    injection: CheckResult | None = None,
    paths: list[str] | None = None,
    output_index: int | None = None,
) -> GateDecision:
    """Decide whether to keep one review output.

    `reasons` lists the findings that drop it. `notes` lists findings shown beside it that do not.
    Findings against the built-in general standard are always notes; only your own rules drop.
    """
    resolved = _resolve_mode(output_type, mode)
    planted = injection_findings(injection, paths, output_index)
    rules = _guideline_findings(report)
    reasons = _faithfulness_reasons(report, resolved) + rules.drops + planted.drops
    return GateDecision(
        keep=not reasons, mode=resolved, reasons=reasons, notes=rules.notes + planted.notes
    )


def _resolve_mode(output_type: OutputType | str, mode: GateMode | str | None) -> GateMode:
    resolved = default_mode(output_type)
    if mode is None:
        return resolved
    if mode == "lenient" or mode == "strict":
        return mode
    raise ValueError(f"Unknown gate mode {mode!r}. Choose from: {', '.join(DROPPING_VERDICTS)}.")


def _faithfulness_reasons(report: Report, mode: GateMode) -> list[Finding]:
    result = report.by("faithfulness")
    if result is None:
        return []
    dropping = DROPPING_VERDICTS[mode]
    return [f for f in result.findings if f.verdict in dropping]


def _guideline_findings(report: Report) -> FindingSplit:
    result = report.by(GUIDELINES_CHECK)
    if result is None:
        return FindingSplit()
    if result.metadata.get("builtin"):
        return FindingSplit(notes=[f for f in result.findings if f.severity is not Severity.PASS])
    return FindingSplit(
        drops=[f for f in result.findings if f.severity is Severity.FAIL],
        notes=[f for f in result.findings if f.severity is Severity.WARN],
    )
