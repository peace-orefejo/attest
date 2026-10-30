"""Measured layer-one recall and false-positive guardrails."""

import json
from pathlib import Path

from attest.checks.injection import check_injection
from attest.trajectory import Step, ToolCall, Trajectory

CORPUS = json.loads((Path(__file__).parent / "fixtures" / "injection_corpus.json").read_text())


def _verdicts(text: str) -> set[str]:
    traj = Trajectory(
        task="Read this content.",
        final_answer="Done.",
        steps=[Step(tool_call=ToolCall(name="read", output=text))],
    )
    return {finding.verdict for finding in check_injection(traj).findings}


def test_default_detector_corpus_metrics():
    malicious_detected = sum(
        bool(_verdicts(text) & {"suspicious", "possible_injection"}) for text in CORPUS["malicious"]
    )
    benign_suspicious = sum("suspicious" in _verdicts(text) for text in CORPUS["benign"])
    benign_possible = sum("possible_injection" in _verdicts(text) for text in CORPUS["benign"])

    recall = malicious_detected / len(CORPUS["malicious"])
    false_positive_rate = benign_suspicious / len(CORPUS["benign"])
    possible_rate = benign_possible / len(CORPUS["benign"])

    assert recall >= 0.9, f"recall regressed to {recall:.1%}"
    assert false_positive_rate <= 0.1, f"false-positive rate regressed to {false_positive_rate:.1%}"
    assert possible_rate <= 0.1, f"possible-injection rate regressed to {possible_rate:.1%}"
