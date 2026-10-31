"""Structured LLM output (native Anthropic, instructor elsewhere). The single LLM chokepoint."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Hashable
from typing import TYPE_CHECKING, Literal, TypeVar, cast

import instructor
from pydantic import BaseModel

from ..prompts.guard import GUARD
from .budget import before_call, record_cache_hit, record_completion
from .client import resolve_client
from .errors import api_error, is_empty_response
from .protocol import LLMClient
from .response_cache import cache_key, response_cache

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam, ChatCompletionUserMessageParam

T = TypeVar("T", bound=BaseModel)
Reuse = Literal["prefix", "full"]

_EPHEMERAL = {"type": "ephemeral"}
_EMPTY_RESPONSE_MESSAGE = (
    "The provider returned no parseable content after several attempts — often a "
    "thinking model exhausting its output-token budget, or a safety/recitation block. "
    "Try a larger max_tokens or a different model."
)


def call(
    *,
    system: str,
    user: str,
    output: type[T],
    max_tokens: int = 4096,
    client: LLMClient | None = None,
    attempts: int = 3,
    sample: int = 0,
    prefix: str = "",
    reuse: Reuse | None = None,
) -> T:
    """Return a validated instance of the Pydantic `output` model from the LLM.

    Thinking models (e.g. Gemini 2.5) can spend their whole output budget reasoning
    and return an empty candidate, which surfaces as a `'NoneType' ... 'parts'` crash.
    Those are transient, so retry a few times, then fail with a clear message. A response
    that isn't an `output` instance (such as None) is retried the same way. Provider HTTP
    errors and other exceptions are raised at once; `BudgetExceeded` is raised before a call.

    `prefix` is shared material (e.g. the evidence) placed first in the user turn so provider
    prompt caches can reuse it. `reuse` says what the caller will resend: "prefix" or the
    "full" prompt; on Anthropic it places cache breakpoints there, elsewhere caching is implicit.
    """
    store = response_cache.get()
    key = cache_key(system, user, output, sample, prefix) if store is not None else ""
    if store is not None and key in store:
        record_cache_hit()
        hit = store[key]
        return hit if isinstance(hit, output) else output.model_validate(hit)

    resolved = client or resolve_client()
    guarded_system = f"{GUARD}\n\n{system}"
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": guarded_system},
        _user_message(resolved, prefix, user, reuse),
    ]
    last_error: Exception | None = None
    for _ in range(max(1, attempts)):
        before_call(guarded_system, prefix, user)
        try:
            result: object = _create(resolved, output, max_tokens, messages)
        except Exception as error:
            hard_error = api_error(error)
            if hard_error is not None and hard_error is not error:
                raise hard_error from error
            if hard_error is not None or not is_empty_response(error):
                raise
            last_error = error
            continue
        if not isinstance(result, output):
            last_error = TypeError(f"Expected {output.__name__}, got {type(result).__name__}.")
            continue
        if store is not None:
            store[key] = result
        return result
    raise RuntimeError(_EMPTY_RESPONSE_MESSAGE) from last_error


def vote(
    *,
    system: str,
    user: str,
    output: type[T],
    key: Callable[[T], Hashable],
    samples: int = 3,
    client: LLMClient | None = None,
) -> T:
    """Self-consistency: sample the judge `samples` times and return the majority `key(...)`.

    Dampens LLM-judge non-determinism (e.g. Gemini is not truly greedy even at temperature 0).
    Stops early once a verdict holds a strict majority, since the remaining samples can no
    longer change the outcome.
    """
    total = max(1, samples)
    results: list[T] = []
    tally: Counter[Hashable] = Counter()
    for sample in range(total):
        result = call(
            system=system,
            user=user,
            output=output,
            client=client,
            sample=sample,
            reuse="full" if total > 1 else None,
        )
        results.append(result)
        tally[key(result)] += 1
        if tally.most_common(1)[0][1] > total // 2:
            break
    winner = tally.most_common(1)[0][0]
    return next(result for result in results if key(result) == winner)


def _user_message(
    client: LLMClient, prefix: str, user: str, reuse: Reuse | None
) -> ChatCompletionUserMessageParam:
    if getattr(client, "provider", None) != instructor.Provider.ANTHROPIC or reuse is None:
        return {"role": "user", "content": f"{prefix}\n\n{user}" if prefix else user}
    return cast(
        "ChatCompletionUserMessageParam",
        {"role": "user", "content": _cached_blocks(prefix, user, reuse)},
    )


def _cached_blocks(prefix: str, user: str, reuse: Reuse) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    if prefix:
        blocks.append({"type": "text", "text": prefix, "cache_control": _EPHEMERAL})
    tail: dict[str, object] = {"type": "text", "text": user}
    if reuse == "full":
        tail["cache_control"] = _EPHEMERAL
    blocks.append(tail)
    return blocks


def _create(
    client: LLMClient,
    output: type[T],
    max_tokens: int,
    messages: list[ChatCompletionMessageParam],
) -> T:
    with_completion = getattr(client, "create_with_completion", None)
    if with_completion is None:
        return client.create(
            response_model=output, max_tokens=max_tokens, temperature=0, messages=messages
        )
    result, completion = with_completion(
        response_model=output, max_tokens=max_tokens, temperature=0, messages=messages
    )
    record_completion(completion)
    return result
