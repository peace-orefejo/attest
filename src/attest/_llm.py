"""Compatibility path for attest.core.llm model calls."""

from .core.llm.calls import call, vote
from .core.llm.context import _resolve_client as _resolve_client
from .core.llm.context import using

__all__ = ["call", "vote", "using"]
