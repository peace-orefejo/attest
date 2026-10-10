"""Live model listing from each provider's SDK, with the curated list as fallback."""

from __future__ import annotations

from .env import resolve_key
from .providers import _spec, curated_models


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
