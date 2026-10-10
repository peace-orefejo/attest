"""Provider registry: Anthropic / OpenAI / Gemini — keys, default models, clients."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol, TypeVar

import instructor
from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel

DEFAULT_PROVIDER = "anthropic"

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    def create(self, *, response_model: type[T], messages: Any, max_tokens: int,
               **kwargs: Any) -> T: ...


@dataclass(frozen=True)
class _Provider:
    name: str
    prefix: str
    env_keys: tuple[str, ...]
    default_model: str
    models: tuple[str, ...]


_REGISTRY: dict[str, _Provider] = {
    "anthropic": _Provider(
        name="anthropic",
        prefix="anthropic",
        env_keys=("ANTHROPIC_API_KEY",),
        default_model="claude-haiku-4-5",
        models=(
            "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5",
            "claude-opus-5", "claude-sonnet-5",
            "claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5",
        ),
    ),
    "openai": _Provider(
        name="openai",
        prefix="openai",
        env_keys=("OPENAI_API_KEY",),
        default_model="gpt-5.6-luna",
        models=("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"),
    ),
    "gemini": _Provider(
        name="gemini",
        prefix="google",
        env_keys=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        default_model="gemini-3.6-flash",
        models=(
            "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite",
            "gemini-2.5-pro",
        ),
    ),
}


def providers() -> list[str]:
    return list(_REGISTRY)


def _spec(provider: str) -> _Provider:
    try:
        return _REGISTRY[provider]
    except KeyError:
        raise ValueError(
            f"Unknown provider {provider!r}. Choose from: {', '.join(_REGISTRY)}."
        ) from None


def default_model(provider: str) -> str:
    return _spec(provider).default_model


def curated_models(provider: str) -> list[str]:
    return list(_spec(provider).models)


@lru_cache(maxsize=1)
def load_env() -> None:
    """Load a `.env` from the working directory (or a parent) without overriding real env vars."""
    load_dotenv(find_dotenv(usecwd=True))


def resolve_key(provider: str, key: str | None = None) -> str | None:
    if key:
        return key
    load_env()
    for env in _spec(provider).env_keys:
        value = os.getenv(env)
        if value:
            return value
    return None


_SAMPLING_MODELS = re.compile(r"claude-(3|(opus|sonnet|haiku)-4-[0-6](\b|-))")


class AnthropicClient:
    """Structured output through Anthropic's native `messages.parse` (no forced tool use).

    Claude 5.5-generation models reject forced `tool_choice`, `anthropic` 1.x dropped the
    `temperature` keyword, and Claude Opus 4.7+ rejects sampling parameters outright, so this
    path uses JSON-schema structured outputs and only sends `temperature` to models that take it.
    """

    def __init__(self, model: str, api_key: str | None = None) -> None:
        from anthropic import Anthropic

        self.model = model
        self.client = Anthropic(api_key=api_key) if api_key else Anthropic()

    def create(self, *, response_model: type[T], messages: Any, max_tokens: int,
               temperature: float | None = None, **kwargs: Any) -> T:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [m for m in messages if m["role"] != "system"]
        extra: dict[str, Any] = {}
        if temperature is not None and _SAMPLING_MODELS.match(self.model):
            extra["extra_body"] = {"temperature": temperature}
        if system:
            extra["system"] = system
        response = self.client.messages.parse(
            model=self.model, max_tokens=max_tokens, messages=turns,
            output_format=response_model, **extra, **kwargs,
        )
        if response.parsed_output is None:
            raise RuntimeError(
                f"{self.model} returned no structured output (stop_reason="
                f"{response.stop_reason!r}). Try a larger max_tokens or a different model."
            )
        return response.parsed_output


def build_client(
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
    key: str | None = None,
) -> LLMClient:
    """Build a structured-output client for `provider`/`model`, key from arg or env."""
    spec = _spec(provider)
    model = model or spec.default_model
    resolved = resolve_key(provider, key)
    if provider == "anthropic":
        return AnthropicClient(model, resolved)
    target = f"{spec.prefix}/{model}"
    if resolved:
        return instructor.from_provider(target, api_key=resolved)
    return instructor.from_provider(target)


def _gemini_chat_models(models) -> list[str]:
    names = []
    for m in models:
        actions = getattr(m, "supported_actions", None)
        if actions is None or "generateContent" in actions:
            names.append(m.name.removeprefix("models/"))
    return names


def fetch_models(provider: str, key: str | None = None) -> list[str]:
    """Fetch the live model list from the provider's SDK (needs a key)."""
    spec = _spec(provider)
    resolved = resolve_key(provider, key)
    if not resolved:
        raise ValueError(
            f"A {provider} API key is required to list models live "
            f"(set {' or '.join(spec.env_keys)}, or pass key=...)."
        )

    if provider == "anthropic":
        from anthropic import Anthropic
        return [m.id for m in Anthropic(api_key=resolved).models.list()]

    if provider == "openai":
        from openai import OpenAI
        return sorted(m.id for m in OpenAI(api_key=resolved).models.list())

    if provider == "gemini":
        from google import genai
        return _gemini_chat_models(genai.Client(api_key=resolved).models.list())

    raise ValueError(f"Live model listing is not implemented for {provider!r}.")


def list_models(provider: str, key: str | None = None) -> list[str]:
    """Live list if a key resolves (arg or env), else the curated shortlist."""
    if resolve_key(provider, key):
        return fetch_models(provider, key)
    return curated_models(provider)
