"""The combined report — offline, with injected fake faithfulness functions."""

import pytest

from attest import Artifact
from attest.results import Finding, Report, Severity
from attest.scoring.report import evaluate
from attest.trajectory import Step, ToolCall, Trajectory


def _fake_extract(_answer):
    return ["claim A", "claim B"]


def _fake_verify(claims, _evidence) -> list[Finding]:
    out = []
    for claim in claims:
        if "A" in claim:
            out.append(Finding(severity=Severity.PASS, verdict="supported", subject=claim))
        else:
            out.append(Finding(severity=Severity.FAIL, verdict="unsupported", subject=claim))
    return out


def _traj():
    return Trajectory(
        task="do it",
        allowed_tools=["search", "summarize"],
        steps=[
            Step(tool_call=ToolCall(name="search", arguments={}, output="found it")),
            Step(tool_call=ToolCall(name="summarize", arguments={}, output="summary")),
        ],
        final_answer="A and B",
    )


def test_evaluate_combines_both_dimensions():
    report = evaluate(_traj(), extract=_fake_extract, verify=_fake_verify)
    assert isinstance(report, Report)
    assert report.by("faithfulness").score == 0.5
    assert report.by("tool_use").score == 1.0
    assert report.overall_score == 0.75
    assert report.passed is False


def test_report_serializes_to_json():
    report = evaluate(_traj(), extract=_fake_extract, verify=_fake_verify)
    js = report.model_dump_json()
    assert '"overall_score"' in js
    assert '"check"' in js
    assert '"findings"' in js
    assert '"prompt_version"' in js


@pytest.mark.parametrize("checks", [[], ["faithfullness"], ["tool_use", "tool_use"]])
def test_evaluate_rejects_invalid_check_selection(checks):
    with pytest.raises(ValueError):
        evaluate(_traj(), checks=checks, extract=_fake_extract, verify=_fake_verify)


def test_evaluate_rejects_unknown_answer_kind():
    with pytest.raises(ValueError, match="answer kind"):
        evaluate(
            _traj(),
            answer_kind="creative",
            extract=_fake_extract,
            verify=_fake_verify,
        )


def test_user_upload_is_not_used_as_faithfulness_evidence():
    traj = _traj()
    traj.artifacts.append(
        Artifact(
            name="untrusted.txt",
            source="user_upload",
            text="A fabricated claim that must not become evidence.",
        )
    )
    seen = {}

    def capture(claims, evidence):
        seen["evidence"] = evidence
        return _fake_verify(claims, evidence)

    evaluate(traj, checks=["faithfulness"], extract=_fake_extract, verify=capture)
    assert "fabricated claim" not in seen["evidence"]
