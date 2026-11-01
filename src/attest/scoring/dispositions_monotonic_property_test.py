"""Property tests: a stricter policy never weakens a verdict, and nothing unjudged passes."""

import pytest

pytest.importorskip("hypothesis")

from hypothesis import given
from hypothesis import strategies as st

from attest.disposition_rules import Disposition, disposition_for, is_unjudged
from attest.results import Finding, Report
from attest.scoring.dispositions import apply_verdict_policy
from attest.scoring.dispositions_property_test import RANK, policies, reports
from attest.scoring.verdict_policy import ToolUsePolicy, VerdictPolicy

TOOL_USE_FIELDS = (
    "on_disallowed_tool",
    "on_unhandled_error",
    "on_claimed_success",
    "on_unnecessary_call",
)


def _max(first: Disposition, second: Disposition) -> Disposition:
    return first if RANK[first] >= RANK[second] else second


def _floor(first: float | None, second: float | None) -> float | None:
    floors = [floor for floor in (first, second) if floor is not None]
    return max(floors) if floors else None


def _stricter(base: VerdictPolicy, other: VerdictPolicy) -> VerdictPolicy:
    """A policy at least as strict as `base` on every field."""
    tool_use = {
        field: _max(getattr(base.tool_use, field), getattr(other.tool_use, field))
        for field in TOOL_USE_FIELDS
    }
    min_score = {
        check: _floor(base.min_score.get(check), other.min_score.get(check)) or 0.0
        for check in {*base.min_score, *other.min_score}
    }
    return VerdictPolicy(
        tool_use=ToolUsePolicy(**tool_use),
        on_inconclusive_faithfulness=_max(
            base.on_inconclusive_faithfulness, other.on_inconclusive_faithfulness
        ),
        on_injection_warning=_max(base.on_injection_warning, other.on_injection_warning),
        min_score=min_score,
        min_claim_coverage=_floor(base.min_claim_coverage, other.min_claim_coverage),
    )


policy_pairs = st.tuples(policies, policies).map(lambda pair: (pair[0], _stricter(*pair)))


def _dispositions(report: Report) -> list[Disposition]:
    return [d for result in report.results for d in result.dispositions]


@given(reports, policy_pairs)
def test_a_stricter_policy_never_gives_a_weaker_verdict(report, pair):
    lenient, strict = (apply_verdict_policy(report, policy) for policy in pair)
    assert RANK[strict.verdict] >= RANK[lenient.verdict]
    for weak, strong in zip(_dispositions(lenient), _dispositions(strict), strict=True):
        assert RANK[strong] >= RANK[weak]


def _judged(finding: Finding) -> Finding:
    """The same finding as if it had been checked, to read the rule its check would apply."""
    verdict = "anything" if finding.verdict == "unchecked" else finding.verdict
    metadata = {**finding.metadata, "checked": True}
    return finding.model_copy(update={"verdict": verdict, "metadata": metadata})


def _inconclusive_claim(check: str, finding: Finding) -> bool:
    return check == "faithfulness" and finding.verdict == "unverifiable"


@given(reports, st.none() | policies)
def test_an_unjudged_finding_is_never_weaker_than_review_or_its_rule(report, policy):
    active = policy or VerdictPolicy()
    applied = apply_verdict_policy(report, active)
    for result in applied.results:
        for finding in result.findings:
            if not is_unjudged(finding) or _inconclusive_claim(result.check, finding):
                continue
            assert finding.disposition is not None
            rule = disposition_for(result.check, _judged(finding), active)
            assert RANK[finding.disposition] >= max(RANK["review"], RANK[rule])


@given(reports, policies)
def test_unchecked_claims_follow_the_inconclusive_faithfulness_rule(report, policy):
    applied = apply_verdict_policy(report, policy)
    for result in applied.results:
        for finding in result.findings:
            if _inconclusive_claim(result.check, finding) and is_unjudged(finding):
                assert finding.disposition is not None
                assert RANK[finding.disposition] >= RANK[policy.on_inconclusive_faithfulness]
