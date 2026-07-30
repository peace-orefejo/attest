"""The class entry point: Attest(provider=..., model=..., key=...).evaluate(traj)."""

from __future__ import annotations

import contextlib
from typing import Callable, Sequence

import instructor

from ._llm import using
from .checks.injection import DEFAULT_DETECTORS, InjectionDetector, check_injection
from .checks.role import check_role_adherence
from .checks.judge_baseline import JudgeVerdict, naive_judge
from .checks.tool_use import check_tool_use
from .checks.verify import MAX_CLAIMS, extract_claims
from .providers import DEFAULT_PROVIDER, build_client, default_model, list_models, providers
from .results import CheckResult, Report
from .scoring.report import DEFAULT_CHECKS, evaluate, validate_evaluation_options
from .scoring.stats import Proportion, wilson_interval
from .trajectory import Trajectory


class Attest:
    """A configured evaluator. Pick a provider + model once; evaluate many trajectories."""

    def __init__(
        self,
        key: str | None = None,
        *,
        provider: str = DEFAULT_PROVIDER,
        model: str | None = None,
        client: instructor.Instructor | None = None,
    ) -> None:
        self.provider = provider
        self.model = model or default_model(provider)
        self._key = key
        self._client = client

    def _llm_context(self, required: bool = True):
        if not required:
            return contextlib.nullcontext()
        if self._client is None:
            self._client = build_client(self.provider, self.model, self._key)
        return using(self._client)

    def evaluate(
        self,
        traj: Trajectory,
        *,
        checks: Sequence[str] = DEFAULT_CHECKS,
        appropriate: bool = False,
        answer_kind: str = "factual",
        deep: bool = True,
        max_claims: int = MAX_CLAIMS,
        extract: Callable[[str], list[str]] = extract_claims,
        verify=None,
    ) -> Report:
        selected = validate_evaluation_options(checks, answer_kind)
        faithfulness_needs_llm = (
            "faithfulness" in selected and (extract is extract_claims or verify is None)
        )
        needs_llm = (
            faithfulness_needs_llm
            or "role" in selected
            or ("injection" in selected and deep)
            or ("tool_use" in selected and appropriate)
        )
        with self._llm_context(needs_llm):
            return evaluate(
                traj,
                checks=selected,
                appropriate=appropriate,
                answer_kind=answer_kind,
                deep=deep,
                max_claims=max_claims,
                extract=extract,
                verify=verify,
            )

    def tool_use(self, traj: Trajectory, *, appropriate: bool = False) -> CheckResult:
        with self._llm_context(appropriate):
            return check_tool_use(traj, appropriate=appropriate)

    def injection(
        self,
        traj: Trajectory,
        *,
        deep: bool = False,
        detectors: Sequence[InjectionDetector] = DEFAULT_DETECTORS,
    ) -> CheckResult:
        with self._llm_context(deep):
            return check_injection(traj, deep=deep, detectors=detectors)

    def role_adherence(self, traj: Trajectory) -> CheckResult:
        with self._llm_context():
            return check_role_adherence(traj)

    def judge(self, traj: Trajectory) -> JudgeVerdict:
        with self._llm_context():
            return naive_judge(traj)

    @staticmethod
    def stats(successes: int, n: int) -> Proportion:
        return wilson_interval(successes, n)

    @staticmethod
    def providers() -> list[str]:
        return providers()

    @staticmethod
    def models(provider: str, key: str | None = None) -> list[str]:
        return list_models(provider, key)
