from __future__ import annotations

import typer

from ...scoring.stats import wilson_interval


def stats(successes: int, n: int) -> None:
    """Report a pass rate with a Wilson 95% confidence interval."""
    typer.echo(wilson_interval(successes, n).pct())
