"""Compatibility path for attest.core.llm providers and clients."""

from .core.llm.catalog import _gemini_chat_models as _gemini_chat_models
from .core.llm.catalog import fetch_models, list_models
from .core.llm.clients import AnthropicClient, LLMClient, build_client
from .core.llm.env import load_env, resolve_key
from .core.llm.providers import DEFAULT_PROVIDER, curated_models, default_model, providers

__all__ = [
    "AnthropicClient", "LLMClient", "build_client",
    "load_env", "resolve_key",
    "DEFAULT_PROVIDER", "curated_models", "default_model", "providers",
    "fetch_models", "list_models",
]
