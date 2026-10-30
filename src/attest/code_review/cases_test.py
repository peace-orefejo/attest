import json
from pathlib import Path

import pytest

from attest import Trajectory
from attest.code_review.models import OUTPUT_TYPES

CASES_PATH = Path(__file__).parent / "fixtures" / "code_review_cases.json"
CASES = json.loads(CASES_PATH.read_text())["cases"]
KINDS = set(OUTPUT_TYPES)


def test_case_ids_are_unique():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))


def test_every_kind_has_both_labels():
    for kind in KINDS:
        labels = {c["expect"] for c in CASES if c["kind"] == kind}
        assert labels == {"flag", "pass"}, kind


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case_is_a_valid_run_with_evidence(case):
    assert case["kind"] in KINDS
    assert case["expect"] in {"flag", "pass"}
    assert case["why"].strip()
    traj = Trajectory.model_validate(case["run"])
    assert traj.has_evidence()
    assert traj.final_answer.strip()
    for _, call in traj.tool_calls():
        assert call.name in (traj.allowed_tools or [])
