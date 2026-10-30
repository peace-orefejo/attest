"""Untrusted content models shared by text, document, and image inspection."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .utils.json_types import JsonObject

ArtifactSource = Literal["tool_output", "user_upload", "retrieved_file"]


class Artifact(BaseModel):
    """A file or text attachment observed during an agent trajectory.

    Exactly one content field is required. Binary content is represented as base64 for
    portable trajectories; ``path`` is useful for local evaluation. Extractors intentionally
    live outside this model so merely loading a trajectory never opens a file.
    """

    id: str | None = None
    name: str | None = None
    media_type: str | None = None
    source: ArtifactSource = "tool_output"
    text: str | None = None
    data_base64: str | None = None
    path: str | None = None
    sha256: str | None = None
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _one_content_source(self) -> Artifact:
        supplied = sum(value is not None for value in (self.text, self.data_base64, self.path))
        if supplied != 1:
            raise ValueError("An artifact requires exactly one of: text, data_base64, or path.")
        return self


class TextSegment(BaseModel):
    """Extracted untrusted text with enough provenance to explain a detection."""

    text: str
    location: str
    source_kind: str
    subject: str
    step: int | None = None
    extraction_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: JsonObject = Field(default_factory=dict)


class Detection(BaseModel):
    verdict: Literal["suspicious", "possible_injection", "unscanned_content"] = "suspicious"
    detector: str
    category: str
    matched_text: str
    location: str
    subject: str
    step: int | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: JsonObject = Field(default_factory=dict)
