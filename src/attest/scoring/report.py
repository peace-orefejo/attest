"""The combined report: run the chosen checks, return one Report of CheckResults."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import partial

from ..checks.injection import check_injection
from ..checks.profiles import SUPPORTED_ANSWER_KINDS, resolve_answer_kind
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
from .dispositions import apply_verdict_policy
from .verdict_policy import VerdictPolicy

DEFAULT_CHECKS = ("faithfulness", "tool_use")
SUPPORTED_CHECKS = ("faithfulness", "tool_use", "injection", "role")


def validate_evaluation_options(
    checks: Sequence[str], answer_kind: str, max_claims: int = MAX_CLAIMS
) -> tuple[str, ...]:
    """Validate public evaluator options before any checks or LLM calls run."""
    if max_claims < 0:
        raise ValueError(f"max_claims must be 0 or more, not {max_claims}.")
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
    verdict_policy: VerdictPolicy | None = None,
) -> Report:
    """
    Run the chosen checks and return one Report. `checks` picks any of
    "faithfulness", "tool_use", "injection", "role" (default: faithfulness + tool_use).
    `answer_kind` is "factual", "plan", "code" or "auto"; "auto" picks factual or code
    from the tool evidence and records the choice in the report metadata.
    Faithfulness/role and injection's `deep` pass need an API key; the tool-use and
    shallow-injection paths do not. `max_claims` caps how many claims faithfulness checks.
    `verdict_policy` sets each finding's disposition and so the report's `verdict`
    (default: `VerdictPolicy()`).
    """
    selected = validate_evaluation_options(checks, answer_kind, max_claims)
    resolved = resolve_answer_kind(traj, answer_kind)

    extractor: ExtractFn = (
        partial(extract_claims, answer_kind=resolved.kind, task=traj.task)
        if extract is extract_claims
        else extract
    )
    verifier: VerifyFn = verify or partial(verify_claims, answer_kind=resolved.kind)

    runners: dict[str, Callable[[], CheckResult]] = {
        "faithfulness": lambda: judge_trajectory(traj, extractor, verifier, max_claims=max_claims),
        "tool_use": lambda: check_tool_use(traj, appropriate=appropriate),
        "injection": lambda: check_injection(traj, deep=deep),
        "role": lambda: check_role_adherence(traj),
    }
    results: list[CheckResult] = [runners[c]() for c in selected]
    report = Report(results=results, metadata=resolved.metadata)
    return apply_verdict_policy(report, verdict_policy)
