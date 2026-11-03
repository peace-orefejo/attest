"""Replace a run's excluded artifacts with a note, before any check reads or scans them."""

from __future__ import annotations

import os
from pathlib import Path, PurePath

from pydantic import BaseModel, Field

from ..content import Artifact
from ..results import CheckResult, Report
from ..trajectory import Step, Trajectory
from .rules import Exclusions, excluded_note

ARTIFACTS_EXCLUDED = "artifacts_excluded"
_ARTIFACT_CHECKS = frozenset({"faithfulness", "injection"})


class ExcludedRun(BaseModel):
    """The run with excluded artifacts swapped for notes, and where those artifacts were."""

    run: Trajectory
    excluded: list[str] = Field(default_factory=list[str])


def exclude_artifacts(traj: Trajectory, exclusions: Exclusions) -> ExcludedRun:
    """Swap every artifact whose `path` or `name` is excluded for a one-line text note.

    The note keeps the artifact's place, so other artifacts keep their locations. Tool
    outputs are not files, so they are never matched.
    """
    if not exclusions.active:
        return ExcludedRun(run=traj)
    excluded: list[str] = []
    steps: list[Step] = []
    for index, step in enumerate(traj.steps):
        call = step.tool_call
        if call is None or not call.artifacts:
            steps.append(step)
            continue
        prefix = f"steps[{index}].tool_call.artifacts"
        artifacts = _swap(call.artifacts, prefix, exclusions, excluded)
        updated = call.model_copy(update={"artifacts": artifacts})
        steps.append(step.model_copy(update={"tool_call": updated}))
    run_level = _swap(traj.artifacts, "artifacts", exclusions, excluded)
    if not excluded:
        return ExcludedRun(run=traj)
    run = traj.model_copy(update={"steps": steps, "artifacts": run_level})
    return ExcludedRun(run=run, excluded=excluded)


def record_excluded(target: Report | CheckResult, excluded: list[str]) -> None:
    """Add `artifacts_excluded` to a report (and its checks that read artifacts) or a result."""
    if not excluded:
        return
    target.metadata[ARTIFACTS_EXCLUDED] = list(excluded)
    if isinstance(target, Report):
        for result in target.results:
            if result.check in _ARTIFACT_CHECKS:
                result.metadata[ARTIFACTS_EXCLUDED] = list(excluded)


def is_excluded_artifact(artifact: Artifact, exclusions: Exclusions) -> bool:
    """True when the artifact's name or path is excluded, as written or with symlinks resolved.

    An absolute path inside the working directory is matched relative to it; any other
    absolute path is matched from every one of its segments.
    """
    return any(exclusions.excludes(candidate) for candidate in _candidates(artifact))


def _swap(
    artifacts: list[Artifact], prefix: str, exclusions: Exclusions, excluded: list[str]
) -> list[Artifact]:
    swapped: list[Artifact] = []
    for index, artifact in enumerate(artifacts):
        if is_excluded_artifact(artifact, exclusions):
            excluded.append(f"{prefix}[{index}]")
            swapped.append(_note(artifact))
        else:
            swapped.append(artifact)
    return swapped


def _note(artifact: Artifact) -> Artifact:
    label = artifact.name or artifact.path or artifact.id or "artifact"
    return Artifact(
        id=artifact.id,
        name=artifact.name,
        source=artifact.source,
        text=excluded_note(label),
        metadata={"excluded": True},
    )


def _candidates(artifact: Artifact) -> list[str]:
    candidates = [artifact.name] if artifact.name else []
    if not artifact.path:
        return candidates
    for path in (artifact.path, _resolved(artifact.path)):
        if path is not None:
            candidates.append(_within_cwd(path))
    return list(dict.fromkeys(candidates))


def _resolved(path: str) -> str | None:
    try:
        return os.path.realpath(path)
    except (OSError, ValueError):
        return None


def _within_cwd(path: str) -> str:
    if not PurePath(path).is_absolute():
        return path
    absolute = Path(os.path.normpath(path))
    for root in _cwd_forms():
        try:
            return absolute.relative_to(root).as_posix()
        except ValueError:
            continue
    return path


def _cwd_forms() -> list[Path]:
    cwd = Path.cwd()
    return list(dict.fromkeys([cwd, cwd.resolve()]))
