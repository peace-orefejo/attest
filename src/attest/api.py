"""The class entry point: Attest(provider=..., model=..., key=...).evaluate(traj)."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Generator, Mapping, Sequence
from contextlib import AbstractContextManager

from .checks.artifact_evidence import ArtifactExtraction, extracting_artifacts
from .checks.injection import DEFAULT_DETECTORS, InjectionDetector, check_injection
from .checks.judge_baseline import JudgeVerdict, naive_judge
from .checks.role import check_role_adherence
from .checks.tool_use import check_tool_use
from .checks.verify import MAX_CLAIMS, ExtractFn, VerifyFn, extract_claims
from .code_review import EvidenceLimits, PullRequest, ReviewOutput, ReviewResult
from .code_review import review as review_outputs
from .code_review import write_review as write_pr_review
from .code_review.guidelines import GuidelinesInput
from .code_review.models import GateMode
from .exclusions import ExclusionsInput, as_exclusions, exclude_artifacts, record_excluded
from .extraction import ExtractionLimits
from .llm import Budget, DiskCache, LLMClient, Usage, metering, using, using_cache
from .llm.response_cache import ResponseStore
from .policy import EvaluationPolicy, PolicyInput, check_policy, load_policy
from .providers import (
    DEFAULT_PROVIDER,
    build_client,
    default_model,
    list_models,
    providers,
    resolve_key,
)
from .results import CheckResult, Report
from .scoring.dispositions import apply_verdict_policy
from .scoring.report import DEFAULT_CHECKS, evaluate, validate_evaluation_options
from .scoring.stats import Proportion, wilson_interval
from .scoring.verdict_policy import VerdictPolicy
from .trajectory import Trajectory
from .utils.json_types import JsonObject

CacheOption = bool | ResponseStore | str | os.PathLike[str]


class Attest:
    """A configured evaluator. Pick a provider + model once; evaluate many trajectories.

    `extract_artifacts=True` lets faithfulness read binary (`data_base64`) artifacts as
    evidence, through the same bounded extraction the injection scan uses; `path` artifacts
    are read from disk only when `allow_paths=True` too. Without it, only text artifacts and
    tool outputs are evidence.

    `exclude` takes a list of gitignore-style patterns, a `Path` to a pattern file, or an
    `Exclusions` from `load_exclusions`, for files attest must leave out (a bare string raises
    `TypeError`): artifacts whose path or name matches are never read, scanned or sent to a
    model, and code review leaves those files' diffs and reads out.
    """

    def __init__(
        self,
        key: str | None = None,
        *,
        provider: str = DEFAULT_PROVIDER,
        model: str | None = None,
        client: LLMClient | None = None,
        policy: PolicyInput = None,
        enforce_policy: bool = True,
        cache: CacheOption = False,
        budget: Budget | None = None,
        extract_artifacts: bool = False,
        allow_paths: bool = False,
        verdict_policy: VerdictPolicy | None = None,
        exclude: ExclusionsInput = None,
    ) -> None:
        self.provider = provider
        self.model = model or default_model(provider)
        self._key = key
        self._client = client
        self.policy = load_policy(policy)
        self.enforce_policy = enforce_policy
        self._cache = _response_store(cache, provider=provider, model=self.model)
        self.budget = budget
        self.verdict_policy = verdict_policy or VerdictPolicy()
        self.usage = Usage()
        self.artifact_extraction = ArtifactExtraction(
            enabled=extract_artifacts, allow_paths=allow_paths
        )
        self.exclusions = as_exclusions(exclude)

    def evaluate(
        self,
        traj: Trajectory,
        *,
        checks: Sequence[str] = DEFAULT_CHECKS,
        appropriate: bool = False,
        answer_kind: str = "factual",
        deep: bool = True,
        max_claims: int = MAX_CLAIMS,
        extract: ExtractFn = extract_claims,
        verify: VerifyFn | None = None,
        enforce_policy: bool | None = None,
    ) -> Report:
        selected = validate_evaluation_options(checks, answer_kind, max_claims)
        hidden = exclude_artifacts(traj, self.exclusions)
        traj = hidden.run
        policy = self._active_policy(enforce_policy)
        needs_llm = _checks_need_llm(
            selected, appropriate=appropriate, deep=deep, extract=extract, verify=verify
        ) or (policy is not None and policy.needs_llm)
        needs_llm = needs_llm or ("tool_use" in selected and self._has_credentials())
        before = self.usage.model_copy()
        with self._llm_context(needs_llm), extracting_artifacts(self.artifact_extraction):
            report = evaluate(
                traj,
                checks=selected,
                appropriate=appropriate,
                answer_kind=answer_kind,
                deep=deep,
                max_claims=max_claims,
                extract=extract,
                verify=verify,
                verdict_policy=self.verdict_policy,
            )
            if policy is not None:
                report.results.append(check_policy(traj, policy))
                report.metadata.update(self.policy_identity())
                report = apply_verdict_policy(report, self.verdict_policy)
        report.metadata["usage"] = self.usage.since(before).as_dict()
        record_excluded(report, hidden.excluded)
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
        max_claims: int = MAX_CLAIMS,
    ) -> ReviewResult:
        """Check every output of a code review and decide which to keep, in one call.

        Pass `guidelines` (markdown paths or text) to use the team's review rules; without them
        the built-in general standard applies. With no `outputs`, attest writes the review itself.
        `max_claims` caps how many claims of each output are checked; an output with more is
        dropped, since the rest were never checked.
        """
        validate_evaluation_options(("faithfulness",), answer_kind, max_claims)

        def grade(run: Trajectory) -> Report:
            return self.evaluate(
                run, checks=("faithfulness",), answer_kind=answer_kind, max_claims=max_claims
            )

        with self._llm_context():
            return review_outputs(
                pr,
                outputs,
                evaluate=grade,
                guidelines=guidelines,
                follow_guidelines=follow_guidelines,
                modes=modes,
                deep=deep,
                limits=limits,
                exclude=self.exclusions,
            )

    def write_review(
        self,
        pr: PullRequest,
        *,
        guidelines: GuidelinesInput = None,
        limits: EvidenceLimits | None = None,
    ) -> list[ReviewOutput]:
        """Write a review of the pull request without checking it: issues, summaries, overview."""
        with self._llm_context():
            return write_pr_review(
                pr, guidelines=guidelines, limits=limits, exclude=self.exclusions
            )

    def policy_check(self, traj: Trajectory) -> CheckResult:
        """Evaluate the instance policy directly without running the standard checks."""
        if self.policy is None:
            raise ValueError("No evaluation policy is configured on this Attest instance.")
        hidden = exclude_artifacts(traj, self.exclusions)
        with self._llm_context(self.policy.needs_llm):
            result = check_policy(hidden.run, self.policy)
        record_excluded(result, hidden.excluded)
        return result

    def policy_identity(self) -> JsonObject:
        if self.policy is None:
            return {}
        return {
            "policy": {
                "name": self.policy.name,
                "version": self.policy.version,
                "hash": self.policy.hash,
            }
        }

    def tool_use(
        self, traj: Trajectory, *, appropriate: bool = False, check_answer: bool | None = None
    ) -> CheckResult:
        """Run the tool-use check. `check_answer=True` reads the final answer for unrecovered
        tool errors without the per-call tool-choice check; it defaults to `appropriate`."""
        answer = appropriate if check_answer is None else check_answer
        hidden = exclude_artifacts(traj, self.exclusions)
        with self._llm_context(appropriate or answer):
            result = check_tool_use(hidden.run, appropriate=appropriate, check_answer=answer)
        record_excluded(result, hidden.excluded)
        return result

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
        hidden = exclude_artifacts(traj, self.exclusions)
        with self._llm_context(deep):
            result = check_injection(
                hidden.run,
                deep=deep,
                detectors=detectors,
                extract_files=extract_files,
                allow_paths=allow_paths,
                extraction_limits=extraction_limits,
            )
        record_excluded(result, hidden.excluded)
        return result

    def role_adherence(self, traj: Trajectory) -> CheckResult:
        hidden = exclude_artifacts(traj, self.exclusions)
        with self._llm_context():
            result = check_role_adherence(hidden.run)
        record_excluded(result, hidden.excluded)
        return result

    def judge(self, traj: Trajectory) -> JudgeVerdict:
        with self._llm_context():
            return naive_judge(exclude_artifacts(traj, self.exclusions).run)

    @staticmethod
    def stats(successes: int, n: int) -> Proportion:
        return wilson_interval(successes, n)

    @staticmethod
    def providers() -> list[str]:
        return providers()

    @staticmethod
    def models(provider: str, key: str | None = None) -> list[str]:
        return list_models(provider, key)

    def _active_policy(self, enforce_policy: bool | None) -> EvaluationPolicy | None:
        enforce = self.enforce_policy if enforce_policy is None else enforce_policy
        return self.policy if enforce else None

    def _llm_context(self, required: bool = True) -> AbstractContextManager[None]:
        if not required:
            return contextlib.nullcontext()
        return self._scoped_llm(self._resolved_client())

    def _has_credentials(self) -> bool:
        return self._client is not None or resolve_key(self.provider, self._key) is not None

    def _resolved_client(self) -> LLMClient:
        if self._client is None:
            self._client = build_client(self.provider, self.model, self._key)
        return self._client

    @contextlib.contextmanager
    def _scoped_llm(self, client: LLMClient) -> Generator[None, None, None]:
        with contextlib.ExitStack() as stack:
            stack.enter_context(using(client))
            stack.enter_context(metering(self.usage, self.budget))
            if self._cache is not None:
                stack.enter_context(using_cache(self._cache))
            yield


def _response_store(cache: CacheOption, *, provider: str, model: str) -> ResponseStore | None:
    if cache is True:
        return {}
    if cache is False:
        return None
    if isinstance(cache, str | os.PathLike):
        return DiskCache(cache, provider=provider, model=model)
    return cache


def _checks_need_llm(
    selected: Sequence[str],
    *,
    appropriate: bool,
    deep: bool,
    extract: ExtractFn,
    verify: VerifyFn | None,
) -> bool:
    faithfulness = "faithfulness" in selected and (extract is extract_claims or verify is None)
    return (
        faithfulness
        or "role" in selected
        or ("injection" in selected and deep)
        or ("tool_use" in selected and appropriate)
    )
