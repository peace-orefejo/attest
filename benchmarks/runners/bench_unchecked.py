"""Spot a check result that is partly unchecked, so it is never graded as a confident label.

When a model call inside a check fails (a missing or rejected key, a timeout, a malformed
reply), attest reports the affected finding as `unchecked`, or as an `unverifiable` claim with
`metadata["checked"]` false. Read as a prediction, that can pass for a clean label: an
injection run whose deep check failed reads `none`, an unverified claim reads `unverifiable`
and a tool error whose answer check failed reads `error_silent`. The graders raise
`UncheckedResult` instead, so the case is recorded as errored and counts against coverage.
"""

from __future__ import annotations

from attest import CheckResult

UNCHECKED = "unchecked"


class UncheckedResult(RuntimeError):
    """A check couldn't judge part of the case, so the case isn't graded."""


def raise_if_unchecked(result: CheckResult | None, *, answer_checked: bool = True) -> None:
    """Raise `UncheckedResult` if any finding of `result` wasn't judged.

    `answer_checked=False` (an offline run, where no model reads the final answer) leaves a
    tool error's `unchecked` recovery alone: it is the documented offline prediction, not a
    failure.
    """
    if result is None:
        return
    for finding in result.findings:
        recovery = finding.metadata.get("recovery")
        if (
            finding.verdict == UNCHECKED
            or finding.metadata.get("checked") is False
            or (answer_checked and recovery == UNCHECKED)
        ):
            where = f"step {finding.step}" if finding.step is not None else repr(finding.subject)
            raise UncheckedResult(f"{result.check} left {where} unchecked: {finding.reason}")
