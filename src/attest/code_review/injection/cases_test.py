import json
from pathlib import Path

import pytest

from attest.code_review.injection import check_code_injection
from attest.code_review.models import INJECTION_VERDICTS, PullRequest, ReviewOutput

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "code_injection_cases.json"
CASES = json.loads(FIXTURE.read_text())["cases"]


def test_fixture_has_planted_and_look_alike_cases():
    kinds = {case["kind"] for case in CASES}
    assert kinds == {"planted", "look_alike"}
    assert {case["label"] for case in CASES} == set(INJECTION_VERDICTS)
    assert len({case["id"] for case in CASES}) == len(CASES)


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_deterministic_layers_match_label(case, no_model):
    pr = PullRequest(**case["pr"])
    outputs = [ReviewOutput(**item) for item in case.get("outputs", [])]
    result = check_code_injection(pr, outputs, deep=False)
    assert result.metadata["verdict"] == case["label"]
    assert result.passed is (case["label"] in ("clean", "suspicious"))
    assert result.metadata["coverage_incomplete"] is False
    expect = case.get("expect")
    if expect:
        strongest = [f for f in result.findings if f.verdict == case["label"]]
        assert any(
            all(f.metadata.get(key) == value for key, value in expect.items()) for f in strongest
        ), [f.metadata for f in strongest]
