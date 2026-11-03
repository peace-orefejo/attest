"""Provider clients turn a reasoning level into request settings and report a cut-off answer."""

import types

import pytest
from anthropic import Omit

import attest.llm.structured as llm
from attest.checks.verify import VerdictOut
from attest.llm import TruncatedOutput, recording_reasoning, using_reasoning
from attest.llm.anthropic_client import AnthropicClient
from attest.llm.instructor_client import InstructorClient
from attest.llm.reasoning import REASONING_ALLOWANCE, ReasoningPolicy
from attest.llm.usage import token_counts

OUT = VerdictOut(verdict="supported")


class _Parsed:
    def __init__(self, parsed_output, stop_reason="end_turn"):
        self.parsed_output = parsed_output
        self.stop_reason = stop_reason
        self.usage = types.SimpleNamespace(input_tokens=10, output_tokens=7)


class _FakeMessages:
    def __init__(self, result):
        self.result = result
        self.kwargs = {}
        self.calls = 0

    def parse(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        return self.result


def _claude(model, result=None):
    client = AnthropicClient(model, api_key="sk-ant-fake")
    fake = _FakeMessages(result or _Parsed(OUT))
    client.client = types.SimpleNamespace(messages=fake)
    return client, fake


def _messages():
    return [{"role": "system", "content": "judge"}, {"role": "user", "content": "claim"}]


def _send(client, reasoning, max_tokens=300):
    return client.create(
        response_model=VerdictOut,
        messages=_messages(),
        max_tokens=max_tokens,
        temperature=0,
        reasoning=reasoning,
    )


def test_haiku_auto_sends_adaptive_thinking_at_low_effort_with_room():
    client, fake = _claude("claude-haiku-5-5")
    assert _send(client, "auto") is OUT
    assert fake.kwargs["thinking"] == {"type": "adaptive"}
    assert fake.kwargs["output_config"] == {"effort": "low"}
    assert fake.kwargs["max_tokens"] == 300 + REASONING_ALLOWANCE["auto"]
    assert fake.kwargs["extra_body"] is None


def test_haiku_off_disables_thinking_and_adds_no_room():
    client, fake = _claude("claude-haiku-5-5")
    _send(client, "off")
    assert fake.kwargs["thinking"] == {"type": "disabled"}
    assert fake.kwargs["max_tokens"] == 300


def test_sonnet_off_sends_between_tools_in_the_body():
    client, fake = _claude("claude-sonnet-5-5")
    _send(client, "off")
    assert fake.kwargs["extra_body"] == {"thinking": {"type": "between_tools"}}
    assert fake.kwargs["output_config"] == {"effort": "low"}
    assert isinstance(fake.kwargs["thinking"], Omit)


def test_opus_gets_only_an_effort_and_room_even_when_off():
    client, fake = _claude("claude-opus-5-5")
    _send(client, "off")
    assert fake.kwargs["output_config"] == {"effort": "low"}
    assert fake.kwargs["extra_body"] is None
    assert fake.kwargs["max_tokens"] == 300 + REASONING_ALLOWANCE["low"]


def test_an_older_claude_model_gets_no_reasoning_setting():
    client, fake = _claude("claude-haiku-4-5")
    _send(client, "high")
    assert fake.kwargs["max_tokens"] == 300
    assert fake.kwargs["extra_body"] == {"temperature": 0}
    assert isinstance(fake.kwargs["output_config"], Omit)


def test_a_max_tokens_stop_with_no_output_is_truncated_output():
    client, _ = _claude("claude-haiku-5-5", _Parsed(None, stop_reason="max_tokens"))
    with pytest.raises(TruncatedOutput, match="max_tokens"):
        _send(client, "auto")


def test_call_does_not_retry_a_truncated_answer():
    client, fake = _claude("claude-haiku-5-5", _Parsed(None, stop_reason="max_tokens"))
    with pytest.raises(TruncatedOutput):
        llm.call(system="s", user="u", output=VerdictOut, client=client, site="role")
    assert fake.calls == 1


def test_call_sends_the_policy_level_for_its_site_and_records_it():
    client, fake = _claude("claude-sonnet-5-5")
    policy = ReasoningPolicy(checks={"guidelines.confirm": "high"})
    with using_reasoning(policy), recording_reasoning() as used:
        llm.call(system="s", user="u", output=VerdictOut, client=client, site="guidelines.confirm")
    assert fake.kwargs["output_config"] == {"effort": "high"}
    assert used == {"guidelines.confirm": "high"}


class IncompleteOutputException(Exception):
    """Named like instructor's error for an answer cut off at the token limit."""


class _InstructorTruncating:
    def create(self, **kwargs):
        raise RuntimeError("retries exhausted") from IncompleteOutputException("length")


def test_instructors_cut_off_error_becomes_truncated_output():
    client = _InstructorTruncating()
    with pytest.raises(TruncatedOutput):
        llm.call(system="s", user="u", output=VerdictOut, client=client)


class _CustomClient:
    def __init__(self):
        self.kwargs = {}

    def create(self, **kwargs):
        self.kwargs = kwargs
        return OUT


def test_a_custom_client_gets_exactly_the_old_arguments():
    client = _CustomClient()
    llm.call(system="s", user="u", output=VerdictOut, client=client, max_tokens=300, site="role")
    assert set(client.kwargs) == {"response_model", "max_tokens", "temperature", "messages"}
    assert client.kwargs["max_tokens"] == 300


class _FakeInstructor:
    provider = "fake"

    def __init__(self):
        self.kwargs = {}

    def create_with_completion(self, **kwargs):
        self.kwargs = kwargs
        return OUT, None


def _instructor(provider, model):
    inner = _FakeInstructor()
    return InstructorClient(inner, provider=provider, model=model), inner


def test_openai_reasoning_sets_effort_room_and_drops_temperature():
    client, inner = _instructor("openai", "gpt-6-luna")
    _send(client, "auto")
    assert inner.kwargs["reasoning_effort"] == "low"
    assert inner.kwargs["max_tokens"] == 300 + REASONING_ALLOWANCE["auto"]
    assert "temperature" not in inner.kwargs


def test_openai_off_sends_none_and_keeps_temperature():
    client, inner = _instructor("openai", "gpt-6-luna")
    _send(client, "off")
    assert inner.kwargs["reasoning_effort"] == "none"
    assert inner.kwargs["temperature"] == 0 and inner.kwargs["max_tokens"] == 300


def test_gemini_auto_sends_dynamic_thinking():
    client, inner = _instructor("gemini", "gemini-3.8-flash")
    _send(client, "auto")
    assert inner.kwargs["thinking_config"] == {"thinking_budget": -1}
    assert inner.kwargs["max_tokens"] == 300 + REASONING_ALLOWANCE["auto"]


def test_an_unlisted_instructor_model_is_called_as_before():
    client, inner = _instructor("openai", "gpt-4o")
    _send(client, "high")
    assert set(inner.kwargs) == {"response_model", "messages", "max_tokens", "temperature"}


def test_gemini_thought_tokens_count_as_output():
    meta = types.SimpleNamespace(
        prompt_token_count=100, candidates_token_count=20, thoughts_token_count=300
    )
    counts = token_counts(types.SimpleNamespace(usage=None, usage_metadata=meta))
    assert counts.output == 320 and counts.input == 100


def test_openai_and_anthropic_output_already_include_reasoning():
    openai_usage = types.SimpleNamespace(
        prompt_tokens=50,
        completion_tokens=400,
        completion_tokens_details=types.SimpleNamespace(reasoning_tokens=350),
    )
    assert token_counts(types.SimpleNamespace(usage=openai_usage)).output == 400
    claude_usage = types.SimpleNamespace(input_tokens=50, output_tokens=400)
    assert token_counts(types.SimpleNamespace(usage=claude_usage)).output == 400
