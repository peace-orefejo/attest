"""The class entry point: Attest(provider=..., model=..., key=...).evaluate(traj)."""

from __future__ import annotations

import contextlib
from typing import Callable, Mapping, Sequence

from .core import CheckResult, Proportion, Report, Trajectory, wilson_interval
from .core.llm import (
    DEFAULT_PROVIDER, LLMClient, build_client, default_model, list_models, providers, using,
)
from .checks.injection import DEFAULT_DETECTORS, InjectionDetector, check_injection
from .extraction import ExtractionLimits
from .checks.role import check_role_adherence
from .checks.judge_baseline import JudgeVerdict, naive_judge
from .checks.tool_use import check_tool_use
from .checks.verify import MAX_CLAIMS, extract_claims
from .code_review import EvidenceLimits, PullRequest, ReviewOutput, ReviewResult
from .code_review import review as review_outputs
from .code_review import write_review as write_pr_review
from .code_review.guidelines import GuidelinesInput
from .code_review.models import GateMode
from .policy import PolicyInput, check_policy, load_policy
from .scoring.report import DEFAULT_CHECKS, evaluate, validate_evaluation_options


class Attest:
    """A configured evaluator. Pick a provider + model once; evaluate many trajectories."""

    def __init__(
        self,
        key: str | None = None,
        *,
        provider: str = DEFAULT_PROVIDER,
        model: str | None = None,
        client: LLMClient | None = None,
        policy: PolicyInput = None,
        enforce_policy: bool = True,
    ) -> None:
        self.provider = provider
        self.model = model or default_model(provider)
        self._key = key
        self._client = client
        self.policy = load_policy(policy)
        self.enforce_policy = enforce_policy

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
        enforce_policy: bool | None = None,
    ) -> Report:
        selected = validate_evaluation_options(checks, answer_kind)
        faithfulness_needs_llm = (
            "faithfulness" in selected and (extract is extract_claims or verify is None)
        )
        policy = self.policy
        enforce = self.enforce_policy if enforce_policy is None else enforce_policy
        needs_llm = (
            faithfulness_needs_llm
            or "role" in selected
            or ("injection" in selected and deep)
            or ("tool_use" in selected and appropriate)
            or (policy is not None and enforce and policy.needs_llm)
        )
        with self._llm_context(needs_llm):
            report = evaluate(
                traj,
                checks=selected,
                appropriate=appropriate,
                answer_kind=answer_kind,
                deep=deep,
                max_claims=max_claims,
                extract=extract,
                verify=verify,
            )
            if policy is not None and enforce:
                report.results.append(check_policy(traj, policy))
                report.metadata.update(self.policy_identity())
            return report

    def review(
        self,
        pr: PullRequest,
        outputs: Sequence[ReviewOutput] | None = None,
        *,
        guidelines: GuidelinesInput = None,
        follow_guidelines: bool = True,
        modes: Mapping[str, GateMode] | None = None,
        deep: bool = True,
        limits: EvidenceLimits | None = None,
        answer_kind: str = "code",
    ) -> ReviewResult:
        """Check every output of a code review and decide which to keep, in one call.

        Pass `guidelines` (markdown paths or text) to use the team's review rules; without them the
        built-in general standard applies. With no `outputs`, attest writes the review itself.
        """
        def grade(run: Trajectory) -> Report:
            return self.evaluate(run, checks=("faithfulness",), answer_kind=answer_kind)

        with self._llm_context():
            return review_outputs(pr, outputs, evaluate=grade, guidelines=guidelines,
                                  follow_guidelines=follow_guidelines, modes=modes, deep=deep, limits=limits)

    def write_review(
        self,
        pr: PullRequest,
        *,
        guidelines: GuidelinesInput = None,
        limits: EvidenceLimits | None = None,
    ) -> list[ReviewOutput]:
        """Write a review of the pull request without checking it: issues, file summaries and an overview."""
        with self._llm_context():
            return write_pr_review(pr, guidelines=guidelines, limits=limits)

    def policy_check(self, traj: Trajectory) -> CheckResult:
        """Evaluate the instance policy directly without running the standard checks."""
        if self.policy is None:
            raise ValueError("No evaluation policy is configured on this Attest instance.")
        with self._llm_context(self.policy.needs_llm):
            return check_policy(traj, self.policy)

    def policy_identity(self) -> dict:
        if self.policy is None:
            return {}
        return {"policy": {"name": self.policy.name, "version": self.policy.version,
                           "hash": self.policy.hash}}

    def tool_use(self, traj: Trajectory, *, appropriate: bool = False) -> CheckResult:
        with self._llm_context(appropriate):
            return check_tool_use(traj, appropriate=appropriate)

    def injection(
        self,
        traj: Trajectory,
        *,
        deep: bool = False,
        detectors: Sequence[InjectionDetector] = DEFAULT_DETECTORS,
        extract_files: bool = True,
        allow_paths: bool = False,
        extraction_limits: ExtractionLimits = ExtractionLimits(),
    ) -> CheckResult:
        with self._llm_context(deep):
            return check_injection(
                traj, deep=deep, detectors=detectors, extract_files=extract_files,
                allow_paths=allow_paths, extraction_limits=extraction_limits,
            )

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
