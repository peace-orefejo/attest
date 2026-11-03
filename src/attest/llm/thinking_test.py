"""What each reasoning level sends to each listed model, and nothing for any other model."""

import pytest

from attest.llm.thinking import (
    CLAUDE_MODELS,
    GEMINI_MODELS,
    OPENAI_MODELS,
    claude_plan,
    gemini_plan,
    openai_plan,
)
from attest.providers import curated_models

LEVELS = ("auto", "off", "low", "medium", "high")


def test_auto_on_claude_is_adaptive_thinking_at_low_effort():
    for model in CLAUDE_MODELS:
        plan = claude_plan(model, "auto")
        assert plan is not None and plan.effort == "low" and plan.room == "auto"
    assert claude_plan("claude-haiku-5-5", "auto").thinking == "adaptive"
    assert claude_plan("claude-sonnet-5-5", "auto").thinking == "adaptive"


def test_off_uses_each_claude_models_own_switch():
    haiku = claude_plan("claude-haiku-5-5", "off")
    sonnet = claude_plan("claude-sonnet-5-5", "off")
    assert (haiku.thinking, haiku.effort, haiku.room) == ("disabled", "low", "off")
    assert (sonnet.thinking, sonnet.effort, sonnet.room) == ("between_tools", "low", "off")


def test_opus_cannot_turn_thinking_off_so_it_only_gets_an_effort():
    for level in LEVELS:
        plan = claude_plan("claude-opus-5-5", level)
        assert plan.thinking is None
    off = claude_plan("claude-opus-5-5", "off")
    assert off.effort == "low" and off.room == "low"


@pytest.mark.parametrize("level", ["low", "medium", "high"])
def test_named_levels_map_to_the_same_effort_on_claude(level):
    plan = claude_plan("claude-haiku-5-5", level)
    assert (plan.thinking, plan.effort, plan.room) == ("adaptive", level, level)


def test_dated_claude_ids_match_their_family():
    assert claude_plan("claude-haiku-5-5-20260101", "auto") is not None


@pytest.mark.parametrize(
    "model", ["claude-haiku-4-5", "claude-3-5-sonnet-latest", "claude-fable-5-1", "my-model"]
)
def test_unknown_or_older_claude_models_get_no_reasoning_setting(model):
    assert all(claude_plan(model, level) is None for level in LEVELS)


def test_openai_auto_is_low_effort_and_off_is_none():
    for model in OPENAI_MODELS:
        assert openai_plan(model, "auto").effort == "low"
        off = openai_plan(model, "off")
        assert off.effort == "none" and off.room == "off" and off.takes_temperature
    assert not openai_plan("gpt-6-luna", "high").takes_temperature
    assert openai_plan("gpt-4o", "auto") is None


def test_gemini_auto_is_dynamic_thinking():
    for model in GEMINI_MODELS:
        assert gemini_plan(model, "auto").config() == {"thinking_budget": -1}
    assert gemini_plan("gemini-2.0-flash", "auto") is None


def test_gemini_off_uses_the_models_lowest_level():
    assert gemini_plan("gemini-3.8-flash", "off").config() == {"thinking_level": "MINIMAL"}
    assert gemini_plan("gemini-4-argon", "off").config() == {"thinking_level": "LOW"}
    assert gemini_plan("models/gemini-3.8-flash", "high").config() == {"thinking_level": "HIGH"}


def test_every_curated_model_but_fable_is_in_the_table():
    listed = {*CLAUDE_MODELS, *OPENAI_MODELS, *GEMINI_MODELS}
    curated = {m for p in ("anthropic", "openai", "gemini") for m in curated_models(p)}
    assert curated - listed == {"claude-fable-5-1"}
