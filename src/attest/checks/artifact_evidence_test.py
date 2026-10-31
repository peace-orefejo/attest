"""Artifact evidence for faithfulness: text always, binary and path files only on opt-in."""

import base64
from pathlib import Path

from attest import Attest
from attest.checks.artifact_evidence import (
    ArtifactExtraction,
    current_extraction,
    extracting_artifacts,
    gather_evidence,
)
from attest.content import Artifact
from attest.extraction import ExtractionLimits
from attest.trajectory import Step, ToolCall, Trajectory

FIXTURE = Path(__file__).parent / "fixtures" / "refund-policy.html"
POLICY = "full refund within 30 days"


def _encoded() -> str:
    return base64.b64encode(FIXTURE.read_bytes()).decode()


def _run(artifact: Artifact) -> Trajectory:
    call = ToolCall(name="fetch_document", output="fetched", artifacts=[artifact])
    return Trajectory(task="t", steps=[Step(tool_call=call)], final_answer="a")


def _binary_run() -> Trajectory:
    return _run(Artifact(name="refund-policy.html", media_type="text/html", data_base64=_encoded()))


def _path_run() -> Trajectory:
    return _run(Artifact(name="refund-policy.html", media_type="text/html", path=str(FIXTURE)))


def test_binary_artifacts_stay_out_of_evidence_without_opt_in():
    gathered = gather_evidence(_binary_run(), ArtifactExtraction())
    assert POLICY not in gathered.text
    assert "<artifact" not in gathered.text
    assert gathered.metadata() == {"artifacts_unread": ["steps[0].tool_call.artifacts[0]"]}


def test_opted_in_binary_artifacts_are_extracted_into_evidence():
    gathered = gather_evidence(_binary_run(), ArtifactExtraction(enabled=True))
    assert POLICY in gathered.text
    assert '<artifact location="steps[0].tool_call.artifacts[0]"' in gathered.text
    assert 'complete="false"' not in gathered.text
    assert gathered.metadata() == {}


def test_path_artifacts_also_need_allow_paths():
    without = gather_evidence(_path_run(), ArtifactExtraction(enabled=True))
    assert POLICY not in without.text
    assert without.unread == ["steps[0].tool_call.artifacts[0]"]
    allowed = gather_evidence(_path_run(), ArtifactExtraction(enabled=True, allow_paths=True))
    assert POLICY in allowed.text


def test_truncated_extraction_is_marked_incomplete():
    limits = ExtractionLimits(max_chars=20)
    gathered = gather_evidence(_binary_run(), ArtifactExtraction(enabled=True, limits=limits))
    assert 'complete="false"' in gathered.text
    assert gathered.incomplete == ["steps[0].tool_call.artifacts[0]"]


def test_failed_extraction_is_marked_incomplete():
    broken = _run(Artifact(name="x.html", media_type="text/html", data_base64="not base64!"))
    gathered = gather_evidence(broken, ArtifactExtraction(enabled=True))
    assert 'complete="false">\n\n</artifact>' in gathered.text
    assert gathered.incomplete == ["steps[0].tool_call.artifacts[0]"]


def test_artifacts_past_the_artifact_limit_are_marked_incomplete():
    limits = ExtractionLimits(max_artifacts=1)
    run = _binary_run()
    run.artifacts.append(Artifact(media_type="text/plain", data_base64=_encoded()))
    gathered = gather_evidence(run, ArtifactExtraction(enabled=True, limits=limits))
    assert gathered.incomplete == ["steps[0].tool_call.artifacts[0]"]


def test_attest_opt_in_reaches_faithfulness():
    seen: list[str] = []

    def capture(claims: list[str], evidence: str) -> list:
        seen.append(evidence)
        return []

    for enabled in (False, True):
        Attest(client=object(), extract_artifacts=enabled).evaluate(
            _binary_run(), checks=["faithfulness"], extract=lambda _: ["c"], verify=capture
        )
    assert POLICY not in seen[0]
    assert POLICY in seen[1]
    assert current_extraction() == ArtifactExtraction()


def test_extracting_artifacts_restores_the_previous_setting():
    with extracting_artifacts(ArtifactExtraction(enabled=True)):
        assert current_extraction().enabled
    assert not current_extraction().enabled
