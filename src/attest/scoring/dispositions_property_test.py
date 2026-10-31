"""Property tests: the report verdict and the verdict policy, over generated reports."""

import pytest

pytest.importorskip("hypothesis")

from hypothesis import given
from hypothesis import strategies as st

from attest.results import BlockingFinding, CheckResult, Finding, Report, Severity
from attest.scoring.dispositions import apply_verdict_policy
from attest.scoring.verdict_policy import ToolUsePolicy, VerdictPolicy

CHECKS = ["faithfulness", "tool_use", "injection", "role", "policy", "custom"]
VERDICTS = [
    "supported",
    "unsupported",
    "unverifiable",
    "correct",
    "disallowed_tool",
    "error_silent",
    "error_claimed_success",
    "inappropriate",
    "unnecessary_call",
    "incorrect",
    "compromised",
    "suspicious",
    "clean",
    "out_of_scope_complied",
    "violated",
    "anything",
]
RANK = {"pass": 0, "review": 1, "block": 2}

dispositions = st.sampled_from(["pass", "review", "block"])
findings = st.builds(
    Finding,
    severity=st.sampled_from(list(Severity)),
    verdict=st.sampled_from(VERDICTS),
    subject=st.text(max_size=8),
    metadata=st.fixed_dictionaries(
        {},
        optional={
            "allowed": st.booleans(),
            "appropriate": st.booleans(),
            "error_handled": st.booleans(),
        },
    ),
    disposition=st.none() | dispositions,
)
scores = st.none() | st.floats(min_value=0.0, max_value=1.0)
results = st.builds(
    CheckResult,
    check=st.sampled_from(CHECKS),
    passed=st.booleans(),
    score=scores,
    findings=st.lists(findings, max_size=4),
)
reports = st.builds(Report, results=st.lists(results, max_size=4))
policies = st.builds(
    VerdictPolicy,
    tool_use=st.builds(
        ToolUsePolicy,
        on_disallowed_tool=dispositions,
        on_unhandled_error=dispositions,
        on_claimed_success=dispositions,
        on_unnecessary_call=dispositions,
    ),
    on_inconclusive_faithfulness=dispositions,
    on_injection_warning=dispositions,
    min_score=st.dictionaries(st.sampled_from(CHECKS), st.floats(0.0, 1.0), max_size=2),
)


def _all_findings(report: Report) -> list[tuple[str, Finding]]:
    return [(result.check, finding) for result in report.results for finding in result.findings]


@given(reports)
def test_the_verdict_is_the_strictest_disposition_and_blocking_lists_the_blocks(report):
    found = _all_findings(report)
    strictest = max((RANK[f.effective_disposition] for _, f in found), default=0)
    assert RANK[report.verdict] == strictest
    assert report.blocking == [
        BlockingFinding(check=check, verdict=f.verdict, subject=f.subject)
        for check, f in found
        if f.effective_disposition == "block"
    ]
    assert (report.verdict == "block") == bool(report.blocking)


@given(reports, st.none() | policies)
def test_applying_a_policy_is_idempotent_and_leaves_the_input_alone(report, policy):
    before = report.model_dump()
    applied = apply_verdict_policy(report, policy)
    assert report.model_dump() == before
    assert applied is not report
    assert apply_verdict_policy(applied, policy) == applied
    assert all(f.disposition is not None for _, f in _all_findings(applied))


@given(reports, st.none() | policies)
def test_earlier_dispositions_do_not_change_the_outcome(report, policy):
    cleared = report.model_copy(
        update={
            "results": [
                r.model_copy(
                    update={
                        "findings": [f.model_copy(update={"disposition": None}) for f in r.findings]
                    }
                )
                for r in report.results
            ]
        }
    )
    assert apply_verdict_policy(report, policy) == apply_verdict_policy(cleared, policy)


@given(reports, st.none() | policies)
def test_a_policy_changes_only_dispositions(report, policy):
    applied = apply_verdict_policy(report, policy)
    strip = {
        "results": {"__all__": {"findings": {"__all__": {"disposition"}}}},
        "verdict": True,
        "passed": True,
        "blocking": True,
    }
    assert applied.model_dump(exclude=strip) == report.model_dump(exclude=strip)


def _faithfulness(verdicts: list[str], severities: list[Severity], score: float | None):
    return CheckResult(
        check="faithfulness",
        passed=True,
        score=score,
        findings=[
            Finding(severity=severity, verdict=verdict, subject=f"claim {i}")
            for i, (verdict, severity) in enumerate(zip(verdicts, severities, strict=False))
        ],
    )


severity_lists = st.lists(st.sampled_from(list(Severity)), min_size=8, max_size=8)


@given(st.integers(1, 6), severity_lists, scores, st.lists(results, max_size=3))
def test_all_unverifiable_faithfulness_never_passes_by_default(count, severities, score, others):
    faithfulness = _faithfulness(["unverifiable"] * count, severities, score)
    report = Report(results=[faithfulness, *others])
    assert apply_verdict_policy(report).verdict != "pass"


@given(
    st.lists(st.sampled_from(["supported", "unverifiable", "unsupported"]), min_size=1, max_size=6),
    severity_lists,
    scores,
    st.lists(results, max_size=3),
)
def test_any_unsupported_claim_blocks_by_default(verdicts, severities, score, others):
    faithfulness = _faithfulness(verdicts, severities, score)
    report = apply_verdict_policy(Report(results=[faithfulness, *others]))
    if "unsupported" in verdicts:
        assert report.verdict == "block"
        assert any(b.check == "faithfulness" for b in report.blocking)


@given(reports, policies)
def test_a_result_below_its_score_floor_has_no_passing_findings(report, policy):
    applied = apply_verdict_policy(report, policy)
    for result in applied.results:
        floor = policy.min_score.get(result.check)
        if floor is not None and result.score is not None and result.score < floor:
            assert all(f.disposition != "pass" for f in result.findings)
