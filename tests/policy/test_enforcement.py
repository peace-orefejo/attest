"""Policies configured once on Attest are enforced on every evaluation."""

import pytest

from attest import Attest

from ._helpers import _deterministic_policy, _traj


def test_instance_policy_is_automatically_enforced_offline():
    judge = Attest(policy=_deterministic_policy())
    report = judge.evaluate(_traj(), checks=["tool_use"])
    assert report.by("policy").passed is True
    assert report.metadata["policy"]["name"] == "support"
    assert report.metadata["policy"]["version"] == "2.1"
    assert report.metadata["policy"]["hash"].startswith("sha256:")
    assert judge._client is None


def test_policy_violation_fails_whole_report():
    judge = Attest(policy=_deterministic_policy())
    report = judge.evaluate(
        _traj(answer="Your refund is guaranteed."), checks=["tool_use"]
    )
    assert report.by("policy").passed is False
    assert report.passed is False
    assert report.by("policy").failures[0].subject == "no-guarantees"


def test_policy_requires_explicit_opt_out():
    judge = Attest(policy=_deterministic_policy())
    report = judge.evaluate(
        _traj(answer="Your refund is guaranteed."),
        checks=["tool_use"], enforce_policy=False,
    )
    assert report.by("policy") is None
    assert "policy" not in report.metadata


def test_instance_can_disable_policy_by_default():
    judge = Attest(policy=_deterministic_policy(), enforce_policy=False)
    assert judge.evaluate(_traj(), checks=["tool_use"]).by("policy") is None
    assert judge.evaluate(
        _traj(), checks=["tool_use"], enforce_policy=True
    ).by("policy") is not None


def test_policy_check_requires_configured_policy():
    with pytest.raises(ValueError, match="No evaluation policy"):
        Attest().policy_check(_traj())
