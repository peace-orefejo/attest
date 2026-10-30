from __future__ import annotations

import importlib
from collections.abc import Callable


def load_callable(module_name: str, attribute: str) -> Callable[..., object]:
    """Import a callable from an optional, untyped dependency without leaking unknown types."""
    member: object = getattr(importlib.import_module(module_name), attribute)
    if not callable(member):
        raise TypeError(f"{module_name}.{attribute} is not callable")
    return member
