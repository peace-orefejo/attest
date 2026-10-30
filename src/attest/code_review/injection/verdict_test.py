import pytest

from attest.code_review.injection.verdict import (
    blocks,
    hit_verdict,
    overall,
    severity,
    tier,
    with_effect,
)
from attest.results import Severity


def test_tiers():
    assert [tier(c) for c in (1.0, 0.9, 0.89, 0.45, 0.44, 0.0)] == [
        "high",
        "high",
        "medium",
        "medium",
        "low",
        "low",
    ]


@pytest.mark.parametrize(
    "confidence, confirmed, expected",
    [
        (0.95, None, "payload"),
        (0.95, False, "payload"),
        (0.6, True, "payload"),
        (0.6, False, "suspicious"),
        (0.6, None, "suspicious"),
        (0.3, True, "clean"),
    ],
)
def test_hit_verdict(confidence, confirmed, expected):
    assert hit_verdict(confidence, confirmed) == expected


def test_with_effect_only_upgrades_payload():
    assert with_effect("payload", True) == "compromised"
    assert with_effect("payload", False) == "payload"
    assert with_effect("suspicious", True) == "suspicious"


def test_overall_is_most_severe_and_never_clean_when_incomplete():
    assert overall([]) == "clean"
    assert overall(["clean", "payload", "suspicious"]) == "payload"
    assert overall(["compromised", "payload"]) == "compromised"
    assert overall([], coverage_incomplete=True) == "suspicious"
    assert overall(["payload"], coverage_incomplete=True) == "payload"


def test_severity_and_blocks():
    assert severity("clean") is Severity.PASS
    assert severity("suspicious") is Severity.WARN
    assert severity("payload") is Severity.FAIL and severity("compromised") is Severity.FAIL
    assert blocks("payload") and blocks("compromised")
    assert not blocks("suspicious") and not blocks("clean")
