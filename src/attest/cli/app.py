from __future__ import annotations

import typer
from dotenv import load_dotenv

from .commands import demo, injection, models, role, run, stats, tools

load_dotenv()
app = typer.Typer(help="Evidence-grounded evaluation for AI agent trajectories.")

for command in (stats, tools, injection, role, run, demo, models):
    app.command()(command)
