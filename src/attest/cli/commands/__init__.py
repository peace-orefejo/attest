from __future__ import annotations

from .demo import demo
from .injection import injection
from .models import models
from .role import role
from .run import run
from .stats import stats
from .tools import tools

COMMANDS = (run, tools, injection, role, demo, stats, models)

__all__ = ["COMMANDS", "demo", "injection", "models", "role", "run", "stats", "tools"]
