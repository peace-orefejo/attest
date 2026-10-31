"""
Check four outputs from an AI code reviewer against the diff they describe, in one call.

Pass guidelines="REVIEW.md" to use your team's review rules; without them attest applies its
general standard.

Prints the ReviewResult as JSON. The real bug and the accurate summary are kept. The invented
off-by-one and the wrong answer about tax are dropped, with the line of the diff that decided
each one.

    uv run python examples/code_review_gate.py
"""

from __future__ import annotations

import json
from pathlib import Path

from attest import Attest
from attest.code_review import PullRequest, ReviewOutput

DATA = json.loads((Path(__file__).parent / "code_review.json").read_text())
PR = PullRequest.model_validate(DATA["pr"])
OUTPUTS = [ReviewOutput.model_validate(output) for output in DATA["outputs"]]


def main() -> None:
    result = Attest().review(PR, OUTPUTS)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
