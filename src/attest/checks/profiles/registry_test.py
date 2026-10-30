"""The answer-kind registry serves the pinned prompts and rejects unknown kinds."""

import pytest
from pydantic import ValidationError

from attest.checks.profiles import SUPPORTED_ANSWER_KINDS, Profile, get_profile
from attest.prompts.profiles import factual, plan


def test_registry_serves_the_pinned_factual_and_plan_prompts():
    assert get_profile("factual").extract_prompt == factual.EXTRACT_PROMPT
    assert get_profile("factual").verify_prompt == factual.VERIFY_PROMPT
    assert get_profile("plan").extract_prompt == factual.EXTRACT_PROMPT
    assert get_profile("plan").verify_prompt == plan.VERIFY_PROMPT


def test_supported_answer_kinds():
    assert SUPPORTED_ANSWER_KINDS == ("factual", "plan", "code", "auto")


@pytest.mark.parametrize("kind", ["factual", "plan", "code"])
def test_get_profile_returns_matching_kind(kind):
    profile = get_profile(kind)
    assert isinstance(profile, Profile)
    assert profile.kind == kind
    assert profile.extract_prompt and profile.verify_prompt


def test_profile_is_frozen():
    with pytest.raises(ValidationError):
        get_profile("factual").verify_prompt = "changed"


def test_code_profile_has_its_own_prompts():
    code = get_profile("code")
    assert code.extract_prompt != get_profile("factual").extract_prompt
    assert code.verify_prompt not in {get_profile(k).verify_prompt for k in ("factual", "plan")}


def test_unknown_kind_raises():
    with pytest.raises(ValueError, match="Unknown answer kind"):
        get_profile("creative")


def test_auto_must_be_resolved_before_lookup():
    with pytest.raises(ValueError, match="resolved"):
        get_profile("auto")
