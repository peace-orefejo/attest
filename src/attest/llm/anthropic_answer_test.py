from __future__ import annotations

import pytest
from anthropic.types import Message, TextBlock, Usage
from pydantic import BaseModel

from attest.llm.anthropic_answer import structured_answer
from attest.llm.errors import UnreadableOutput


class Verdict(BaseModel):
    verdict: str


def _message(stop_reason: str, text: str) -> Message:
    return Message.model_construct(
        id="msg_1",
        type="message",
        role="assistant",
        model="claude-haiku-5-5",
        content=[TextBlock.model_construct(type="text", text=text)],
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=Usage.model_construct(input_tokens=10, output_tokens=5),
    )


def test_a_refusal_is_never_read_as_an_answer_even_when_its_text_validates():
    response = _message("refusal", '{"verdict": "supported"}')
    with pytest.raises(UnreadableOutput, match="declined") as caught:
        structured_answer(response, Verdict, "claude-haiku-5-5")
    assert caught.value.completion is response


def test_a_finished_answer_is_read():
    assert structured_answer(
        _message("end_turn", '{"verdict": "supported"}'), Verdict, "claude-haiku-5-5"
    ) == Verdict(verdict="supported")
