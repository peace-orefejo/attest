"""The single result shape every check returns: CheckResult with a list of Findings."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, computed_field

from .disposition_rules import DEFAULT_RULES, Disposition, disposition_for, result_dispositions
from .prompts.version import PROMPT_VERSION
from .utils.json_types import JsonObject


class Severity(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class Finding(BaseModel):
    severity: Severity
    verdict: str
    subject: str = ""
    reason: str = ""
    evidence: str | None = None
    step: int | None = None
    metadata: JsonObject = Field(default_factory=dict)
    disposition: Disposition | None = None

    @property
    def effective_disposition(self) -> Disposition:
        """The disposition `evaluate()` assigned. Unassigned, and without knowing its check, a
        fail blocks, a finding nothing checked (`unchecked`, or `metadata["checked"]` false) goes
        to review, and the rest pass. `CheckResult.dispositions` also knows the check.
        """
        if self.disposition is not None:
            return self.disposition
        return disposition_for("", self, DEFAULT_RULES)


class BlockingFinding(BaseModel):
    """A finding whose disposition blocked the report."""

    check: str
    verdict: str
    subject: str = ""


class CheckResult(BaseModel):
    check: str
    passed: bool
    score: float | None = None
    summary: str = ""
    findings: list[Finding] = Field(default_factory=list[Finding])
    metadata: JsonObject = Field(default_factory=dict)
    prompt_version: str = PROMPT_VERSION

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.FAIL]

    @property
    def dispositions(self) -> list[Disposition]:
        """Each finding's disposition: the one `evaluate()` assigned, or else the one the
        default `VerdictPolicy()` gives it, so a hand-built report gets the same verdict."""
        defaults = result_dispositions(self.check, self.findings, DEFAULT_RULES)
        return [
            finding.disposition or default
            for finding, default in zip(self.findings, defaults, strict=True)
        ]


class Report(BaseModel):
    results: list[CheckResult]
    metadata: JsonObject = Field(default_factory=dict)

    @computed_field
    @property
    def overall_score(self) -> float | None:
        scored = [r.score for r in self.results if r.score is not None]
        return sum(scored) / len(scored) if scored else None

    @computed_field
    @property
    def passed(self) -> bool:
        """The run passed: its `verdict` is `pass`. False when anything needs review or blocks."""
        return self.verdict == "pass"

    @computed_field
    @property
    def checks_passed(self) -> bool:
        """Every check's own `passed` is true. Ignores dispositions, so a run can have
        `checks_passed` true and still need review; gate on `verdict` or `passed`."""
        return all(r.passed for r in self.results)

    @computed_field
    @property
    def verdict(self) -> Disposition:
        """The strictest disposition among the findings: pass, review or block."""
        dispositions = {d for r in self.results for d in r.dispositions}
        if "block" in dispositions:
            return "block"
        return "review" if "review" in dispositions else "pass"

    @computed_field
    @property
    def blocking(self) -> list[BlockingFinding]:
        return [
            BlockingFinding(check=r.check, verdict=f.verdict, subject=f.subject)
            for r in self.results
            for f, disposition in zip(r.findings, r.dispositions, strict=True)
            if disposition == "block"
        ]

    @computed_field
    @property
    def scores(self) -> dict[str, float | None]:
        return {r.check: r.score for r in self.results}

    @computed_field
    @property
    def claim_coverage(self) -> float | None:
        """Share of the answer's claims faithfulness checked against the evidence.

        None when faithfulness didn't run or the answer made no claims. Kept separate from the
        faithfulness score: 1 claim checked out of 40 can still score 1.0.
        """
        faithfulness = self.by("faithfulness")
        return claim_coverage(faithfulness) if faithfulness is not None else None

    def by(self, check: str) -> CheckResult | None:
        return next((r for r in self.results if r.check == check), None)


def claim_coverage(result: CheckResult) -> float | None:
    """Share of a faithfulness result's claims checked against the evidence, or None."""
    checked, total = result.metadata.get("claims_checked"), result.metadata.get("claims_total")
    if not isinstance(checked, int) or not isinstance(total, int) or total == 0:
        return None
    return checked / total
