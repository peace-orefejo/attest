from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel

from ...content import Artifact, TextSegment
from ...extraction import ExtractionLimits, extract_artifact
from ...trajectory import Trajectory


class ArtifactEntry(BaseModel):
    artifact: Artifact
    location: str
    step: int | None = None


class ExtractionWarning(BaseModel):
    artifact: Artifact
    location: str
    warning: str
    truncated: bool


class CollectedSegments(BaseModel):
    segments: list[TextSegment]
    warnings: list[ExtractionWarning]
    inspected_locations: set[str]
    deferred_locations: set[str]
    chars: int = 0


class BoundedSegments(BaseModel):
    segments: list[TextSegment]
    omitted_segments: int = 0
    omitted_chars: int = 0
    omitted_locations: set[str]

    @property
    def truncated(self) -> bool:
        return self.omitted_segments > 0 or self.omitted_chars > 0


def artifact_location(segment: TextSegment) -> str | None:
    location = segment.metadata.get("artifact_location")
    return location if isinstance(location, str) else None


def artifact_locations(segments: Iterable[TextSegment]) -> set[str]:
    return {location for segment in segments if (location := artifact_location(segment))}


def artifact_entries(traj: Trajectory) -> list[ArtifactEntry]:
    entries = [
        ArtifactEntry(artifact=artifact, location=f"artifacts[{index}]")
        for index, artifact in enumerate(traj.artifacts)
    ]
    for step, call in traj.tool_calls():
        entries.extend(
            ArtifactEntry(
                artifact=artifact,
                location=f"steps[{step}].tool_call.artifacts[{index}]",
                step=step,
            )
            for index, artifact in enumerate(call.artifacts)
        )
    return entries


def direct_segments(traj: Trajectory) -> list[TextSegment]:
    # Artifact text is routed through extract_artifact so it receives the same limits and
    # coverage accounting as embedded files. Tool outputs remain direct segments.
    return [
        segment
        for segment in traj.untrusted_text_segments()
        if segment.source_kind != "artifact_text"
    ]


def collect_segments(
    traj: Trajectory,
    entries: list[ArtifactEntry],
    *,
    extract_files: bool,
    allow_paths: bool,
    limits: ExtractionLimits,
) -> CollectedSegments:
    segments = direct_segments(traj)
    collected = CollectedSegments(
        segments=segments,
        chars=sum(len(segment.text) for segment in segments),
        warnings=[],
        inspected_locations=set(),
        deferred_locations=set(),
    )
    attempts = 0
    for index, entry in enumerate(entries):
        if not _extractable(entry, extract_files):
            continue
        if attempts >= limits.max_artifacts or _scan_budget_spent(collected, limits):
            collected.deferred_locations.update(
                remaining.location
                for remaining in entries[index:]
                if _extractable(remaining, extract_files)
            )
            break
        attempts += 1
        _extract_into(collected, entry, allow_paths=allow_paths, limits=limits)
    return collected


def bound_scan_segments(segments: list[TextSegment], limits: ExtractionLimits) -> BoundedSegments:
    kept: list[TextSegment] = []
    used = 0
    for index, segment in enumerate(segments):
        if len(kept) >= limits.max_scan_segments or used >= limits.max_scan_chars:
            return _omit(kept, segments[index:])
        remaining = limits.max_scan_chars - used
        if len(segment.text) > remaining:
            kept.append(segment.model_copy(update={"text": segment.text[:remaining]}))
            bounded = _omit(kept, segments[index + 1 :])
            bounded.omitted_chars += len(segment.text) - remaining
            if location := artifact_location(segment):
                bounded.omitted_locations.add(location)
            return bounded
        kept.append(segment)
        used += len(segment.text)
    return BoundedSegments(segments=kept, omitted_locations=set())


def _extractable(entry: ArtifactEntry, extract_files: bool) -> bool:
    return entry.artifact.text is not None or extract_files


def _scan_budget_spent(collected: CollectedSegments, limits: ExtractionLimits) -> bool:
    return (
        len(collected.segments) >= limits.max_scan_segments
        or collected.chars >= limits.max_scan_chars
    )


def _extract_into(
    collected: CollectedSegments,
    entry: ArtifactEntry,
    *,
    allow_paths: bool,
    limits: ExtractionLimits,
) -> None:
    outcome = extract_artifact(
        entry.artifact, entry.location, entry.step, limits=limits, allow_paths=allow_paths
    )
    collected.segments.extend(outcome.segments)
    collected.chars += sum(len(segment.text) for segment in outcome.segments)
    if outcome.inspected:
        collected.inspected_locations.add(entry.location)
    if outcome.warning or outcome.truncated:
        collected.warnings.append(
            ExtractionWarning(
                artifact=entry.artifact,
                location=entry.location,
                warning=outcome.warning or "Extraction reached its character limit.",
                truncated=outcome.truncated,
            )
        )


def _omit(kept: list[TextSegment], omitted: list[TextSegment]) -> BoundedSegments:
    return BoundedSegments(
        segments=kept,
        omitted_segments=len(omitted),
        omitted_chars=sum(len(segment.text) for segment in omitted),
        omitted_locations=artifact_locations(omitted),
    )
