from __future__ import annotations

from ...scoring.stats import wilson_interval
from ..json_output import emit, json_command


@json_command("stats")
def stats(successes: int, n: int) -> None:
    """Report a pass rate with a Wilson 95% confidence interval."""
    emit("stats", wilson_interval(successes, n))
