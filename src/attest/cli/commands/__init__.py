from __future__ import annotations

from .demo import demo
from .injection import injection
from .models import models
from .review import review
from .role import role
from .run import run
from .schema import schema
from .stats import stats
from .tools import tools

COMMANDS = (run, tools, injection, role, review, demo, stats, models, schema)

__all__ = [
    "COMMANDS",
    "demo",
    "injection",
    "models",
    "review",
    "role",
    "run",
    "schema",
    "stats",
    "tools",
]
