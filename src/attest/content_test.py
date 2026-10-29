"""Artifact validation and trajectory content provenance."""

import pytest
from pydantic import ValidationError

from attest import Artifact, Trajectory


def test_artifact_requires_exactly_one_content_source():
    with pytest.raises(ValidationError, match="exactly one"):
        Artifact(name="empty.png", media_type="image/png")
    with pytest.raises(ValidationError, match="exactly one"):
        Artifact(text="visible", data_base64="dmVyeQ==")


def test_top_level_artifact_counts_as_evidence():
    traj = Trajectory(
        task="Inspect this image",
        final_answer="It looks safe.",
        artifacts=[Artifact(name="note.png", media_type="image/png", text="hello")],
    )
    assert traj.has_evidence() is True
    assert "note.png" not in traj.evidence()
    assert traj.untrusted_text_segments()[0].subject == "note.png"


def test_user_upload_cannot_become_faithfulness_evidence():
    traj = Trajectory(
        task="Inspect this file",
        final_answer="The balance is one million dollars.",
        artifacts=[
            Artifact(
                name="claim.txt",
                source="user_upload",
                text="The balance is one million dollars.",
            )
        ],
    )
    assert traj.evidence() == ""
