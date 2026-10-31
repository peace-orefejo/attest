"""Faithfulness evidence: tool outputs plus artifacts, with opt-in bounded file extraction."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from pydantic import BaseModel, ConfigDict, Field

from ..content import ArtifactText
from ..extraction import ExtractionLimits, ExtractionOutcome, extract_artifact
from ..trajectory import EvidenceBlock, Trajectory
from ..utils.json_types import JsonObject
from .injection.coverage import ArtifactEntry, artifact_entries


class ArtifactExtraction(BaseModel):
    """Whether faithfulness reads binary and path artifacts, and under which limits."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    allow_paths: bool = False
    limits: ExtractionLimits = ExtractionLimits()


class GatheredEvidence(BaseModel):
    blocks: list[EvidenceBlock]
    unread: list[str] = Field(default_factory=list[str])
    incomplete: list[str] = Field(default_factory=list[str])

    @property
    def text(self) -> str:
        return "\n".join(block.rendered for block in self.blocks)

    def metadata(self) -> JsonObject:
        metadata: JsonObject = {}
        if self.unread:
            metadata["artifacts_unread"] = list(self.unread)
        if self.incomplete:
            metadata["artifacts_incomplete"] = list(self.incomplete)
        return metadata


_NO_EXTRACTION = ArtifactExtraction()
_EXTRACTION: ContextVar[ArtifactExtraction | None] = ContextVar(
    "attest_artifact_extraction", default=None
)


@contextmanager
def extracting_artifacts(options: ArtifactExtraction) -> Generator[None, None, None]:
    """Use `options` for faithfulness evidence within this block."""
    token = _EXTRACTION.set(options)
    try:
        yield
    finally:
        _EXTRACTION.reset(token)


def current_extraction() -> ArtifactExtraction:
    return _EXTRACTION.get() or _NO_EXTRACTION


def gather_evidence(traj: Trajectory, options: ArtifactExtraction) -> GatheredEvidence:
    """Render the run's evidence, reading binary and path artifacts only when opted in."""
    pending = [entry for entry in artifact_entries(traj) if _needs_extraction(entry)]
    readable = [entry for entry in pending if _readable(entry, options)]
    texts = _extract_texts(readable, options)
    return GatheredEvidence(
        blocks=traj.evidence_blocks(texts),
        unread=sorted(entry.location for entry in pending if entry.location not in texts),
        incomplete=sorted(location for location, text in texts.items() if not text.complete),
    )


def _needs_extraction(entry: ArtifactEntry) -> bool:
    return entry.artifact.text is None and entry.artifact.source != "user_upload"


def _readable(entry: ArtifactEntry, options: ArtifactExtraction) -> bool:
    if not options.enabled:
        return False
    return entry.artifact.path is None or options.allow_paths


def _extract_texts(
    entries: list[ArtifactEntry], options: ArtifactExtraction
) -> dict[str, ArtifactText]:
    limits = options.limits
    texts: dict[str, ArtifactText] = {}
    chars = 0
    for index, entry in enumerate(entries):
        room = limits.max_scan_chars - chars
        if index >= limits.max_artifacts or room <= 0:
            texts[entry.location] = ArtifactText(text="", complete=False)
            continue
        outcome = extract_artifact(
            entry.artifact,
            entry.location,
            entry.step,
            limits=limits,
            allow_paths=options.allow_paths,
        )
        full = _outcome_text(outcome)
        texts[entry.location] = ArtifactText(
            text=full[:room], complete=_complete(outcome) and len(full) <= room
        )
        chars += min(len(full), room)
    return texts


def _outcome_text(outcome: ExtractionOutcome) -> str:
    return "\n".join(segment.text for segment in outcome.segments)


def _complete(outcome: ExtractionOutcome) -> bool:
    return outcome.inspected and outcome.warning is None and not outcome.truncated
