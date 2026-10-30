from __future__ import annotations

from pydantic import BaseModel
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from ..checks.judge_baseline import JudgeVerdict
from ..display.checks import header
from ..display.findings import findings_table
from ..display.theme import STYLES, badge, percent, safe
from ..results import CheckResult
from ..trajectory import Trajectory
from ..utils.json_types import JsonObject


class DemoOutcome(BaseModel):
    code: str
    message: str


_OUTCOMES = {
    (True, True): DemoOutcome(
        code="caught", message="attest caught a false claim the LLM judge waved through."
    ),
    (False, True): DemoOutcome(code="both_caught", message="Both caught the problem."),
    (True, False): DemoOutcome(code="both_passed", message="Both agree this answer is sound."),
    (False, False): DemoOutcome(
        code="judge_only", message="The LLM judge flagged something attest's grounding didn't."
    ),
}


class DemoRow(BaseModel):
    trajectory: Trajectory
    verdict: JudgeVerdict
    result: CheckResult

    @property
    def outcome(self) -> DemoOutcome:
        return _OUTCOMES[(self.verdict.passed, bool(self.result.failures))]

    def to_json(self) -> JsonObject:
        return {
            "task": self.trajectory.task,
            "answer": self.trajectory.final_answer,
            "judge": self.verdict.model_dump(mode="json"),
            "attest": self.result.model_dump(mode="json"),
            "outcome": self.outcome.code,
        }


def demo_view(row: DemoRow) -> Group:
    parts: list[RenderableType] = [
        header(Text("TASK", style=STYLES["head"]), row.trajectory.task),
        Text(""),
        _comparison(row),
    ]
    if row.result.failures:
        parts += [Text(""), findings_table(row.result.failures, indent=2)]
    parts += [Text(""), Text(row.outcome.message, style=STYLES["label"])]
    return Group(*parts)


def _comparison(row: DemoRow) -> Table:
    result = row.result
    grounding = f"grounding {percent(result.score)} · {result.summary}"
    rows = Table.grid(padding=(0, 2))
    rows.add_column(no_wrap=True, style=STYLES["head"])
    rows.add_column(no_wrap=True)
    rows.add_column(ratio=1)
    rows.add_row("answer", "", safe(row.trajectory.final_answer))
    rows.add_row("LLM judge", badge(row.verdict.passed), safe(row.verdict.reason, STYLES["muted"]))
    rows.add_row("attest", badge(not result.failures), safe(grounding, STYLES["muted"]))
    return rows
