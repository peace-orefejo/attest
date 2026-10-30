from __future__ import annotations

import typer

from ...scoring.stats import wilson_interval
from ..options import JSON_OPTION
from ..rendering import emit_json


def stats(successes: int, n: int, json_output: bool = JSON_OPTION) -> None:
    """Report a pass rate with a Wilson 95% confidence interval."""
    interval = wilson_interval(successes, n)
    if json_output:
        emit_json(interval.model_dump(mode="json"))
        return
    typer.echo(interval.pct())
