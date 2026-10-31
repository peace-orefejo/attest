"""check_code_injection: segment, detect, confirm, check effect, and report."""

from __future__ import annotations

from ...results import CheckResult, Finding
from ...utils.json_types import JsonObject
from ..models import InjectionVerdict, PullRequest, ReviewOutput
from .bounded import CharBudget
from .confirm import ConfirmOut, confirm
from .detect import detect
from .effect import EffectReport, assess_effect
from .hits import Hit
from .segments import build_segments
from .verdict import blocks, hit_verdict, overall, severity, tier, with_effect

CHECK_NAME = "code_injection"

_REASONS: dict[InjectionVerdict, str] = {
    "clean": "Matched a pattern only as a quoted or low-signal example.",
    "suspicious": "Instruction-like text aimed at a reviewer; not confirmed as an attack.",
    "payload": "Text in the pull request tries to steer an automated reviewer.",
    "compromised": "A review output repeated or obeyed text planted to steer the reviewer.",
}
_SUMMARY_ORDER: tuple[InjectionVerdict, ...] = ("compromised", "payload", "suspicious", "clean")
_LABELS: dict[InjectionVerdict, str] = {"clean": "benign look-alike"}


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
        check=CHECK_NAME,
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


class _Run:
    def __init__(
        self, pr: PullRequest, outputs: list[ReviewOutput], deep: bool, budget: int
    ) -> None:
        self.pr = pr
        self.outputs = outputs
        self.deep = deep
        self.budget = CharBudget(budget)
        self.incomplete = False
        self._confirmed: dict[str, ConfirmOut | None] = {}
        self._effects: dict[tuple[str, str, int], EffectReport] = {}

    def finding(self, hit: Hit) -> Finding:
        answer = self._confirmation(hit)
        verdict = hit_verdict(hit.confidence, answer.steers_reviewer if answer else None)
        reason = answer.reason if answer and answer.reason else _REASONS[verdict]
        metadata: JsonObject = {
            "file": hit.segment.file,
            "line": hit.line,
            "segment_kind": hit.segment.kind,
            "detector": hit.detector,
            "confidence": round(hit.confidence, 3),
            "pattern": hit.pattern,
            "category": hit.category,
        }
        if verdict == "payload" and self.outputs:
            report = self._effect(hit)
            verdict = with_effect(verdict, bool(report.compromised))
            if report.compromised:
                metadata["affected_outputs"] = list(report.compromised)
                reason = " ".join(report.reasons) or _REASONS["compromised"]
        return Finding(
            severity=severity(verdict),
            verdict=verdict,
            subject=hit.segment.subject,
            reason=reason,
            evidence=hit.evidence,
            metadata=metadata,
        )

    def _confirmation(self, hit: Hit) -> ConfirmOut | None:
        if not self.deep or tier(hit.confidence) != "medium":
            return None
        if hit.window not in self._confirmed:
            self._confirmed[hit.window] = confirm(
                hit.window,
                file=hit.segment.file,
                segment_kind=hit.segment.kind,
                signal=f"{hit.detector}:{hit.pattern}",
                budget=self.budget,
            )
            if self._confirmed[hit.window] is None:
                self.incomplete = True
        return self._confirmed[hit.window]

    def _effect(self, hit: Hit) -> EffectReport:
        key = (hit.window, hit.segment.file, hit.line)
        if key not in self._effects:
            report = assess_effect(
                hit.window,
                file=hit.segment.file,
                line=hit.line,
                pr=self.pr,
                outputs=self.outputs,
                deep=self.deep,
                budget=self.budget,
            )
            self.incomplete = self.incomplete or report.unresolved
            self._effects[key] = report
        return self._effects[key]


def _summary(findings: list[Finding], verdict: str, incomplete: bool) -> str:
    counts = {v: sum(f.verdict == v for f in findings) for v in _SUMMARY_ORDER}
    if not findings:
        text = "No reviewer-steering text found in the added lines or PR text."
    else:
        parts = [f"{counts[v]} {_LABELS.get(v, v)}" for v in _SUMMARY_ORDER if counts[v]]
        plural = "s" if len(findings) != 1 else ""
        text = f"{len(findings)} hit{plural}: {', '.join(parts)}. Overall: {verdict}."
    if incomplete:
        text += (
            " Coverage incomplete: the scan or model budget ran out, or a model call failed, "
            "before every hit was checked."
        )
    return text
