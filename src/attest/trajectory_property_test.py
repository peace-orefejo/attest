"""Property tests: a run's evidence is one well-formed block per source, rendered stably."""

import pytest

pytest.importorskip("hypothesis")

from hypothesis import given
from hypothesis import strategies as st

from attest.content import Artifact, ArtifactText
from attest.prompts.evidence_property_test import arguments, hostile_text, tag_counts
from attest.trajectory import Step, ToolCall, Trajectory

text_artifacts = st.builds(
    Artifact,
    name=st.none() | hostile_text,
    source=st.sampled_from(["tool_output", "user_upload", "retrieved_file"]),
    text=hostile_text,
)
path_artifacts = st.builds(
    Artifact,
    name=st.none() | hostile_text,
    source=st.sampled_from(["tool_output", "user_upload", "retrieved_file"]),
    path=st.just("report.pdf"),
)
artifact_lists = st.lists(text_artifacts | path_artifacts, max_size=2)


def _runs(*, with_artifacts: bool) -> st.SearchStrategy[Trajectory]:
    attached = artifact_lists if with_artifacts else st.just([])
    tool_calls = st.builds(
        ToolCall,
        name=hostile_text,
        arguments=arguments,
        output=hostile_text,
        artifacts=attached,
        is_error=st.none() | st.booleans(),
    )
    steps = st.builds(Step, thought=st.none() | hostile_text, tool_call=st.none() | tool_calls)
    return st.builds(
        Trajectory,
        task=hostile_text,
        steps=st.lists(steps, max_size=4),
        artifacts=attached,
        final_answer=hostile_text,
    )


def _artifact_locations(run: Trajectory) -> list[tuple[str, Artifact]]:
    located = [
        (f"steps[{step}].tool_call.artifacts[{index}]", artifact)
        for step, call in run.tool_calls()
        for index, artifact in enumerate(call.artifacts)
    ]
    return located + [(f"artifacts[{i}]", artifact) for i, artifact in enumerate(run.artifacts)]


@st.composite
def runs_with_extraction(draw: st.DrawFn) -> tuple[Trajectory, dict[str, ArtifactText]]:
    run = draw(_runs(with_artifacts=True))
    extracted: dict[str, ArtifactText] = {}
    for location, artifact in _artifact_locations(run):
        if artifact.path is not None and draw(st.booleans()):
            extracted[location] = ArtifactText(
                text=draw(hostile_text), complete=draw(st.booleans())
            )
    return run, extracted


def _expected_artifact_blocks(run: Trajectory, extracted: dict[str, ArtifactText]) -> int:
    return sum(
        artifact.source != "user_upload" and (artifact.text is not None or location in extracted)
        for location, artifact in _artifact_locations(run)
    )


@given(runs_with_extraction())
def test_every_block_has_exactly_one_open_and_one_close_tag(case):
    run, extracted = case
    blocks = run.evidence_blocks(extracted)
    for block in blocks:
        is_tool = block.rendered.startswith("<tool_output ")
        assert block.rendered.startswith("<tool_output " if is_tool else "<artifact ")
        assert tag_counts(block.rendered) == ((1, 1, 0, 0) if is_tool else (0, 0, 1, 1))
    tools = len(run.tool_calls())
    artifacts = _expected_artifact_blocks(run, extracted)
    assert tag_counts(run.evidence(extracted)) == (tools, tools, artifacts, artifacts)
    assert run.evidence(extracted) == "\n".join(block.rendered for block in blocks)
    uploads = {
        loc for loc, artifact in _artifact_locations(run) if artifact.source == "user_upload"
    }
    assert not {block.location for block in blocks} & uploads


@given(runs_with_extraction())
def test_rendering_is_deterministic_and_survives_a_json_round_trip(case):
    run, extracted = case
    first = run.evidence(extracted)
    assert run.evidence(extracted) == first
    assert run.model_copy(deep=True).evidence(dict(extracted)) == first
    restored = Trajectory.model_validate_json(run.model_dump_json())
    assert restored.evidence(extracted) == first


@given(_runs(with_artifacts=False))
def test_a_run_without_artifacts_renders_the_same_after_a_json_round_trip(run):
    restored = Trajectory.model_validate_json(run.model_dump_json())
    assert restored.evidence() == run.evidence()
    assert restored.evidence_blocks() == run.evidence_blocks()
