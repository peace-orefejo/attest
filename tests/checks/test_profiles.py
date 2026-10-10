"""Pin the factual and plan prompts so code-review work can never change them."""

import hashlib

import attest.checks.verify as v

FACTUAL_EXTRACT_SHA256 = "88301d6da5e48f114426d1e9370ced05f5b8d60104b137548f174a36629ef52a"
FACTUAL_VERIFY_SHA256 = "7a295646fe114c400e283887aebfb01dd91b2fa8921ae4f18c3ad2a004c46634"
PLAN_VERIFY_SHA256 = "68005a40e8a530d0b30318500afe3386e74d3fbc799634f827790c882e508afd"
BATCH_INSTRUCTION_SHA256 = "9d0750acd499966dea8345286fd37f79e3e75c5e49732e7184475a99e86f607f"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_factual_extraction_prompt_is_pinned():
    assert _sha256(v._EXTRACT_SYSTEM) == FACTUAL_EXTRACT_SHA256


def test_factual_verification_prompt_is_pinned():
    assert _sha256(v._VERIFY_SYSTEM["factual"]) == FACTUAL_VERIFY_SHA256


def test_plan_verification_prompt_is_pinned():
    assert _sha256(v._VERIFY_SYSTEM["plan"]) == PLAN_VERIFY_SHA256


def test_batch_instruction_is_pinned():
    assert _sha256(v._BATCH_INSTRUCTION) == BATCH_INSTRUCTION_SHA256
