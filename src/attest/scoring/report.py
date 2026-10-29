"""The combined report: run the chosen checks, return one Report of CheckResults."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import partial

from ..checks.injection import check_injection
from ..checks.role import check_role_adherence
from ..checks.tool_use import check_tool_use
from ..checks.verify import (
    MAX_CLAIMS,
    ExtractFn,
    VerifyFn,
    extract_claims,
    judge_trajectory,
    verify_claims,
)
from ..results import CheckResult, Report
from ..trajectory import Trajectory

DEFAULT_CHECKS = ("faithfulness", "tool_use")
SUPPORTED_CHECKS = ("faithfulness", "tool_use", "injection", "role")
SUPPORTED_ANSWER_KINDS = ("factual", "plan")


def validate_evaluation_options(checks: Sequence[str], answer_kind: str) -> tuple[str, ...]:
    """Validate public evaluator options before any checks or LLM calls run."""
    selected = tuple(checks)
    if not selected:
        raise ValueError("At least one check is required.")

    unknown = sorted(set(selected) - set(SUPPORTED_CHECKS))
    if unknown:
        raise ValueError(
            f"Unknown check(s): {', '.join(unknown)}. Choose from: {', '.join(SUPPORTED_CHECKS)}."
        )
    if len(set(selected)) != len(selected):
        raise ValueError("Each check may be selected only once.")
    if answer_kind not in SUPPORTED_ANSWER_KINDS:
        raise ValueError(
            f"Unknown answer kind {answer_kind!r}. "
            f"Choose from: {', '.join(SUPPORTED_ANSWER_KINDS)}."
        )
    return selected


def evaluate(
    traj: Trajectory,
    *,
    checks: Sequence[str] = DEFAULT_CHECKS,
    appropriate: bool = False,
    answer_kind: str = "factual",
    deep: bool = True,
    max_claims: int = MAX_CLAIMS,
    extract: ExtractFn = extract_claims,
    verify: VerifyFn | None = None,
) -> Report:
    """
    Run the chosen checks and return one Report. `checks` picks any of
    "faithfulness", "tool_use", "injection", "role" (default: faithfulness + tool_use).
    Faithfulness/role and injection's `deep` pass need an API key; the tool-use and
    shallow-injection paths do not. `max_claims` caps how many claims faithfulness checks.
    """
    selected = validate_evaluation_options(checks, answer_kind)

    verifier: VerifyFn = verify or partial(verify_claims, answer_kind=answer_kind)

    runners: dict[str, Callable[[], CheckResult]] = {
        "faithfulness": lambda: judge_trajectory(traj, extract, verifier, max_claims=max_claims),
        "tool_use": lambda: check_tool_use(traj, appropriate=appropriate),
        "injection": lambda: check_injection(traj, deep=deep),
        "role": lambda: check_role_adherence(traj),
    }
    results: list[CheckResult] = [runners[c]() for c in selected]
    return Report(results=results)
