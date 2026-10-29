"""check_code_injection: segment, detect, confirm, check effect, and report."""

from __future__ import annotations

from ...core import CheckResult, Finding
from ..models import PullRequest, ReviewOutput
from .bounded import CharBudget
from .confirm import ConfirmOut, confirm
from .detect import Hit, detect
from .effect import EffectReport, assess_effect
from .segments import build_segments
from .verdict import blocks, hit_verdict, overall, severity, tier, with_effect

_REASONS = {
    "clean": "Matched a pattern only as a quoted or low-signal example.",
    "suspicious": "Instruction-like text aimed at a reviewer; not confirmed as an attack.",
    "payload": "Text in the pull request tries to steer an automated reviewer.",
    "compromised": "A review output repeated or obeyed text planted to steer the reviewer.",
}


class _Run:
    def __init__(self, pr: PullRequest, outputs: list[ReviewOutput], deep: bool, budget: int):
        self.pr = pr
        self.outputs = outputs
        self.deep = deep
        self.budget = CharBudget(budget)
        self.incomplete = False
        self._confirmed: dict[str, ConfirmOut | None] = {}
        self._effects: dict[tuple[str, str, int], EffectReport] = {}

    def confirmation(self, hit: Hit) -> ConfirmOut | None:
        if not self.deep or tier(hit.confidence) != "medium":
            return None
        if hit.window not in self._confirmed:
            self._confirmed[hit.window] = confirm(
                hit.window, file=hit.segment.file, segment_kind=hit.segment.kind,
                signal=f"{hit.detector}:{hit.pattern}", budget=self.budget,
            )
            if self._confirmed[hit.window] is None:
                self.incomplete = True
        return self._confirmed[hit.window]

    def effect(self, hit: Hit) -> EffectReport:
        key = (hit.window, hit.segment.file, hit.line)
        if key not in self._effects:
            report = assess_effect(
                hit.window, file=hit.segment.file, line=hit.line, pr=self.pr,
                outputs=self.outputs, deep=self.deep, budget=self.budget,
            )
            self.incomplete = self.incomplete or report.unresolved
            self._effects[key] = report
        return self._effects[key]

    def finding(self, hit: Hit) -> Finding:
        answer = self.confirmation(hit)
        verdict = hit_verdict(hit.confidence, answer.steers_reviewer if answer else None)
        reason = answer.reason if answer and answer.reason else _REASONS[verdict]
        metadata: dict = {
            "file": hit.segment.file,
            "line": hit.line,
            "segment_kind": hit.segment.kind,
            "detector": hit.detector,
            "confidence": round(hit.confidence, 3),
            "pattern": hit.pattern,
            "category": hit.category,
        }
        if verdict == "payload" and self.outputs:
            report = self.effect(hit)
            verdict = with_effect(verdict, bool(report.compromised))
            if report.compromised:
                metadata["affected_outputs"] = report.compromised
                reason = " ".join(report.reasons) or _REASONS["compromised"]
        return Finding(severity=severity(verdict), verdict=verdict, subject=hit.segment.subject,
                       reason=reason, evidence=hit.evidence, metadata=metadata)


def _summary(findings: list[Finding], verdict: str, incomplete: bool) -> str:
    counts = {v: sum(f.verdict == v for f in findings) for v in _REASONS}
    if not findings:
        text = "No reviewer-steering text found in the added lines or PR text."
    else:
        labels = {"clean": "benign look-alike"}
        parts = [f"{counts[v]} {labels.get(v, v)}" for v in ("compromised", "payload", "suspicious", "clean")
                 if counts[v]]
        text = f"{len(findings)} hit{'s' if len(findings) != 1 else ''}: {', '.join(parts)}. Overall: {verdict}."
    if incomplete:
        text += " Coverage incomplete: the scan or model budget ran out before every hit was checked."
    return text


def check_code_injection(
    pr: PullRequest,
    outputs: list[ReviewOutput] | None = None,
    *,
    deep: bool = True,
    budget_chars: int = 8000,
) -> CheckResult:
    """Scan a pull request for text planted to steer an automated reviewer."""
    run = _Run(pr, list(outputs or []), deep, budget_chars)
    segments = build_segments(pr)
    hits, scan_incomplete = detect(segments)
    findings = [run.finding(hit) for hit in hits]
    incomplete = scan_incomplete or run.incomplete
    verdict = overall((f.verdict for f in findings), coverage_incomplete=incomplete)
    return CheckResult(
        check="code_injection",
        passed=not any(blocks(f.verdict) for f in findings),
        summary=_summary(findings, verdict, incomplete),
        findings=findings,
        metadata={
            "coverage_incomplete": incomplete,
            "verdict": verdict,
            "segments_scanned": len(segments),
            "model_calls": run.budget.calls,
            "budget_chars_used": run.budget.total - run.budget.remaining,
        },
    )
