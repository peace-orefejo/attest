"""Load `.env` files and resolve provider API keys from arguments or the environment."""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import find_dotenv, load_dotenv

from .providers import _spec


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
