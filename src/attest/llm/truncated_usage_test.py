"""A cut-off answer from the real provider SDKs: one request, TruncatedOutput, tokens counted.

Each SDK talks to an httpx MockTransport, so the SDK's own parsing runs. The transport comes
from whichever httpx module the installed SDK imports (newer SDKs use `httpx2`).
"""

import importlib
import json
import types

import pytest

import attest.llm.structured as llm
from attest.checks.verify import VerdictOut
from attest.llm import Budget, BudgetExceeded, TruncatedOutput, Usage, metering
from attest.llm.anthropic_client import AnthropicClient
from attest.llm.instructor_client import InstructorClient

PARTIAL = '{"verdict": "supp'


def _httpx(sdk: str):
    base = importlib.import_module(
        f"{sdk}._base_client" if sdk != "google.genai" else f"{sdk}._api_client"
    )
    return getattr(base, "httpx2", None) or base.httpx


def _transport(sdk, body, sent):
    httpx = _httpx(sdk)

    def handler(request):
        sent.append(json.loads(request.content) if request.content else request.url.path)
        return httpx.Response(200, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _claude_message(content, stop_reason):
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 4106},
    }


def _claude(content, stop_reason="max_tokens"):
    from anthropic import Anthropic

    sent = []
    client = AnthropicClient("claude-haiku-5-5", api_key="sk-ant-fake")
    http = _transport("anthropic", _claude_message(content, stop_reason), sent)
    client.client = Anthropic(api_key="sk-ant-fake", http_client=http)
    return client, sent


def _call(client, usage, budget=None):
    with metering(usage, budget):
        return llm.call(system="s", user="u", output=VerdictOut, client=client, site="role")


@pytest.mark.parametrize(
    "content",
    [
        [{"type": "text", "text": PARTIAL}],
        [{"type": "thinking", "thinking": "hmm", "signature": "x"}],
    ],
    ids=["partial_json", "only_thinking"],
)
def test_a_cut_off_claude_answer_is_sent_once_and_its_tokens_count(content):
    client, sent = _claude(content)
    usage = Usage()
    with pytest.raises(TruncatedOutput) as raised:
        _call(client, usage)
    assert len(sent) == 1
    assert raised.value.completion is not None
    assert (usage.calls, usage.input_tokens, usage.output_tokens) == (1, 10, 4106)


def test_a_later_call_is_stopped_by_the_budget_the_cut_off_call_used():
    client, sent = _claude([{"type": "text", "text": PARTIAL}])
    usage = Usage()
    budget = Budget(max_tokens=4200)
    with pytest.raises(TruncatedOutput):
        _call(client, usage, budget)
    with pytest.raises(BudgetExceeded):
        _call(client, usage, budget)
    assert len(sent) == 1


def test_an_unreadable_claude_answer_is_retried_and_every_attempt_counts():
    client, sent = _claude([{"type": "text", "text": "not json"}], stop_reason="end_turn")
    usage = Usage()
    with pytest.raises(RuntimeError, match="no parseable content"):
        _call(client, usage)
    assert len(sent) == 3
    assert usage.output_tokens == 3 * 4106


def test_a_cut_off_openai_answer_is_sent_once_and_its_tokens_count():
    pytest.importorskip("openai")
    import instructor

    arguments = {"name": "VerdictOut", "arguments": PARTIAL}
    body = {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-6-luna",
        "choices": [
            {
                "index": 0,
                "finish_reason": "length",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": "t1", "type": "function", "function": arguments}],
                },
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 300, "total_tokens": 311},
    }
    sent = []
    inner = instructor.from_provider(
        "openai/gpt-6-luna", api_key="sk-fake", http_client=_transport("openai", body, sent)
    )
    usage = Usage()
    with pytest.raises(TruncatedOutput):
        _call(InstructorClient(inner, provider="openai", model="gpt-6-luna"), usage)
    assert len(sent) == 1
    assert (usage.input_tokens, usage.output_tokens) == (11, 300)


@pytest.mark.parametrize(
    "parts",
    [[{"text": PARTIAL}], [], [{"functionCall": {"name": "VerdictOut", "args": {}}}]],
    ids=["partial_text", "no_parts", "partial_call"],
)
def test_a_cut_off_gemini_answer_is_sent_once_and_its_tokens_count(parts):
    genai_types = pytest.importorskip("google.genai.types")
    import instructor

    body = {
        "candidates": [
            {"finishReason": "MAX_TOKENS", "content": {"role": "model", "parts": parts}}
        ],
        "usageMetadata": {
            "promptTokenCount": 11,
            "candidatesTokenCount": 5,
            "thoughtsTokenCount": 295,
        },
    }
    sent = []
    http = _transport("google.genai", body, sent)
    inner = instructor.from_provider(
        "google/gemini-3.8-flash",
        api_key="fake",
        http_options=genai_types.HttpOptions(httpx_client=http),
    )
    usage = Usage()
    with pytest.raises(TruncatedOutput):
        _call(InstructorClient(inner, provider="gemini", model="gemini-3.8-flash"), usage)
    assert len(sent) == 1
    assert (usage.input_tokens, usage.output_tokens) == (11, 300)


class IncompleteOutputException(Exception):
    """Named like instructor's error for an answer cut off at the token limit."""

    def __init__(self, last_completion):
        super().__init__("cut off")
        self.last_completion = last_completion


class _PlainInstructor:
    """A custom client, as a user might pass: instructor raising its own truncation error."""

    def __init__(self):
        self.calls = 0

    def create_with_completion(self, **kwargs):
        self.calls += 1
        usage = types.SimpleNamespace(prompt_tokens=7, completion_tokens=90)
        raise IncompleteOutputException(types.SimpleNamespace(usage=usage))


def test_a_custom_clients_cut_off_answer_counts_its_tokens():
    client = _PlainInstructor()
    usage = Usage()
    with pytest.raises(TruncatedOutput) as raised:
        _call(client, usage)
    assert client.calls == 1
    assert raised.value.completion is not None
    assert (usage.input_tokens, usage.output_tokens) == (7, 90)
