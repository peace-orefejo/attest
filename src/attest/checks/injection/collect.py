"""Gathering of untrusted segments from tool outputs and bounded artifact extraction."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...content import Artifact, TextSegment
from ...extraction import ExtractionLimits, extract_artifact
from ...trajectory import Trajectory

ArtifactEntry = tuple[Artifact, str, int | None]
ExtractionWarning = tuple[Artifact, str, str, bool]


@dataclass
class CollectedSegments:
    segments: list[TextSegment]
    artifact_entries: list[ArtifactEntry]
    extraction_warnings: list[ExtractionWarning] = field(default_factory=list)
    inspected_locations: set[str] = field(default_factory=set)
    deferred_locations: set[str] = field(default_factory=set)


def artifact_entries(traj: Trajectory) -> list[ArtifactEntry]:
    entries: list[ArtifactEntry] = [
        (artifact, f"artifacts[{index}]", None)
        for index, artifact in enumerate(traj.artifacts)
    ]
    for step, tc in traj.tool_calls():
        entries.extend(
            (artifact, f"steps[{step}].tool_call.artifacts[{index}]", step)
            for index, artifact in enumerate(tc.artifacts)
        )
    return entries


def collect_segments(
    traj: Trajectory,
    *,
    extract_files: bool,
    allow_paths: bool,
    limits: ExtractionLimits,
) -> CollectedSegments:
    # Artifact text is routed through extract_artifact below so it receives the same limits
    # and coverage accounting as embedded files. Tool outputs remain direct segments.
    collected = CollectedSegments(
        segments=[
            segment for segment in traj.untrusted_text_segments()
            if segment.source_kind != "artifact_text"
        ],
        artifact_entries=artifact_entries(traj),
    )
    entries = collected.artifact_entries
    extraction_attempts = 0
    pending_chars = sum(len(segment.text) for segment in collected.segments)
    pending_segments = len(collected.segments)
    for entry_index, (artifact, location, step) in enumerate(entries):
        if artifact.text is None and not extract_files:
            continue
        if (extraction_attempts >= limits.max_artifacts
                or pending_segments >= limits.max_scan_segments
                or pending_chars >= limits.max_scan_chars):
            collected.deferred_locations.update(
                remaining_location
                for remaining_artifact, remaining_location, _ in entries[entry_index:]
                if remaining_artifact.text is not None or extract_files
            )
            break
        extraction_attempts += 1
        outcome = extract_artifact(
            artifact, location, step, limits=limits, allow_paths=allow_paths
        )
        collected.segments.extend(outcome.segments)
        pending_segments += len(outcome.segments)
        pending_chars += sum(len(segment.text) for segment in outcome.segments)
        if outcome.inspected:
            collected.inspected_locations.add(location)
        if outcome.warning or outcome.truncated:
            collected.extraction_warnings.append(
                (artifact, location, outcome.warning or "Extraction reached its character limit.",
                 outcome.truncated)
            )
    return collected
