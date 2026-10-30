"""Provider registry: Anthropic / OpenAI / Gemini — keys, default models, clients."""

from __future__ import annotations

import os
from collections.abc import Iterable
from functools import lru_cache
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import instructor
from dotenv import dotenv_values, find_dotenv
from pydantic import BaseModel, ConfigDict

from .utils.imports import load_callable

if TYPE_CHECKING:
    from .llm.protocol import LLMClient

DEFAULT_PROVIDER = "anthropic"


class _Provider(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

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
            "claude-opus-5-5",
            "claude-sonnet-5-5",
            "claude-haiku-5-5",
            "claude-opus-5",
            "claude-sonnet-5",
            "claude-opus-4-8",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
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
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
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
    """Load provider API keys from a `.env` in the working directory (or a parent).

    Only the provider key variables are read, and real environment variables always win, so an
    untrusted repository's `.env` cannot redirect API traffic (e.g. via a base-URL variable).
    """
    path = find_dotenv(usecwd=True)
    if not path:
        return
    wanted = {name for spec in _REGISTRY.values() for name in spec.env_keys}
    for name, value in dotenv_values(path).items():
        if name in wanted and value and not os.getenv(name):
            os.environ[name] = value


def resolve_key(provider: str, key: str | None = None) -> str | None:
    if key:
        return key
    load_env()
    for env in _spec(provider).env_keys:
        value = os.getenv(env)
        if value:
            return value
    return None


def build_client(
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
    key: str | None = None,
) -> LLMClient:
    """Build a structured-output client for `provider`/`model`, key from arg or env.

    Anthropic uses its native structured outputs; the other providers go through instructor.
    """
    spec = _spec(provider)
    model = model or spec.default_model
    resolved = resolve_key(provider, key)
    if provider == "anthropic":
        from .llm.anthropic_client import AnthropicClient

        return AnthropicClient(model, resolved)
    target = f"{spec.prefix}/{model}"
    if resolved:
        return instructor.from_provider(target, api_key=resolved)
    return instructor.from_provider(target)


def _gemini_chat_models(models: Iterable[object]) -> list[str]:
    names: list[str] = []
    for model in models:
        name = getattr(model, "name", None)
        if isinstance(name, str) and _supports_generation(model):
            names.append(name.removeprefix("models/"))
    return names


def _supports_generation(model: object) -> bool:
    actions: object = getattr(model, "supported_actions", None)
    if actions is None:
        return True
    return isinstance(actions, list | tuple | set | frozenset) and "generateContent" in actions


@runtime_checkable
class _ModelListing(Protocol):
    def list(self) -> Iterable[object]: ...


@runtime_checkable
class _ModelsClient(Protocol):
    models: _ModelListing


def _sdk_client(module: str, attribute: str, key: str) -> _ModelsClient:
    client = load_callable(module, attribute)(api_key=key)
    if not isinstance(client, _ModelsClient):
        raise TypeError(f"{module}.{attribute} did not return a client with a models listing.")
    return client


def _model_ids(models: Iterable[object]) -> list[str]:
    return [model_id for model in models if isinstance(model_id := getattr(model, "id", None), str)]


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
        return sorted(_model_ids(_sdk_client("openai", "OpenAI", resolved).models.list()))

    if provider == "gemini":
        return _gemini_chat_models(_sdk_client("google.genai", "Client", resolved).models.list())

    raise ValueError(f"Live model listing is not implemented for {provider!r}.")


def list_models(provider: str, key: str | None = None) -> list[str]:
    """Live list if a key resolves (arg or env), else the curated shortlist."""
    if resolve_key(provider, key):
        return fetch_models(provider, key)
    return curated_models(provider)
