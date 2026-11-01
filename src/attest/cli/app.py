from __future__ import annotations

import typer

from .. import providers
from .commands import COMMANDS
from .usage_errors import JsonUsageGroup

app = typer.Typer(
    cls=JsonUsageGroup, help="Evidence-grounded evaluation for AI agent trajectories."
)


@app.callback()
def _load_workspace_env() -> None:
    providers.load_env()


for command in COMMANDS:
    app.command()(command)
