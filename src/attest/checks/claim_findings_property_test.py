"""Property tests: filling in claims the verifier skipped never hides or invents a verdict."""

import pytest

pytest.importorskip("hypothesis")

from hypothesis import example, given
from hypothesis import strategies as st

from attest.checks.claim_findings import unverifiable, verdict_finding, with_missing_claims
from attest.results import Finding, Severity

CLAIMS = ["Paris has 2.1M people", "Berlin has 3.7M", "Rome is older", "  ", ""]

claims = st.lists(st.sampled_from(CLAIMS) | st.text(max_size=12), max_size=6)
verdicts = st.sampled_from(["supported", "unsupported", "unverifiable"])


def _finding(subject: str, verdict: str) -> Finding:
    if verdict == "unverifiable":
        return unverifiable(subject, "verifier said so")
    return verdict_finding(subject, verdict, "verifier said so", None)


@st.composite
def verifier_output(draw: st.DrawFn, *, exact: bool) -> tuple[list[str], list[Finding]]:
    """Claims, and findings for some of them; `exact` keeps subjects to the claim strings."""
    drawn = draw(claims)
    subjects = st.sampled_from(drawn) if drawn and exact else st.text(max_size=12)
    if drawn and not exact:
        subjects = subjects | st.sampled_from(drawn)
    returned = draw(st.lists(st.builds(_finding, subjects, verdicts), max_size=len(drawn) + 2))
    return drawn, returned


@given(verifier_output(exact=False))
def test_nothing_returned_is_lost_and_only_unverifiable_findings_are_added(case):
    claimed, returned = case
    completed = with_missing_claims(claimed, returned)
    assert len(completed) >= len(claimed)
    assert completed[: len(returned)] == returned
    added = completed[len(returned) :]
    assert all(f.verdict == "unverifiable" and f.severity is Severity.WARN for f in added)
    assert all(f.subject in claimed for f in added)


@given(verifier_output(exact=True))
@example((["a", "b"], [verdict_finding("a", "supported", "", None)] * 2))
def test_every_claim_gets_a_finding_when_subjects_are_the_claims(case):
    claimed, returned = case
    completed = with_missing_claims(claimed, returned)
    subjects = {finding.subject for finding in completed}
    assert set(claimed) <= subjects


@given(verifier_output(exact=True))
def test_claims_with_a_verdict_are_not_filled_in_again(case):
    claimed, returned = case
    if len(returned) < len(claimed):
        return
    if {f.subject for f in returned} >= set(claimed):
        assert with_missing_claims(claimed, returned) == returned
