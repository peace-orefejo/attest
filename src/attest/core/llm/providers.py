"""Provider registry: Anthropic / OpenAI / Gemini — env keys, default models, curated lists."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PROVIDER = "anthropic"


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
