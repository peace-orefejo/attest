"""The data model for an agent run. Tool outputs are the evidence attest trusts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

from pydantic import BaseModel, Field

from .content import Artifact, ArtifactText, TextSegment
from .prompts.evidence import artifact_block, evidence_block
from .utils.json_types import JsonObject


class ToolCall(BaseModel):
    name: str
    arguments: JsonObject = Field(default_factory=dict)
    output: str = ""
    artifacts: list[Artifact] = Field(default_factory=list[Artifact])


class Step(BaseModel):
    thought: str | None = None
    tool_call: ToolCall | None = None


class IndexedToolCall(NamedTuple):
    step: int
    call: ToolCall


class EvidenceBlock(BaseModel):
    """One rendered evidence block, with where it came from and its unescaped text."""

    location: str
    text: str
    rendered: str


class Trajectory(BaseModel):
    task: str
    system_prompt: str | None = None
    allowed_tools: list[str] | None = None
    steps: list[Step] = Field(default_factory=list[Step])
    artifacts: list[Artifact] = Field(default_factory=list[Artifact])
    final_answer: str

    def evidence(self, extracted: Mapping[str, ArtifactText] | None = None) -> str:
        """The real tool outputs and artifacts — the only text attest trusts.

        Each tool output is one <tool_output> block, followed by an <artifact> block for each
        of its artifacts; run-level artifacts come last. User uploads are never evidence.
        Artifact text is used directly; binary and path artifacts appear only when `extracted`
        holds their text, keyed by location. Block tags inside content are escaped, so content
        cannot close its block or fake another block.
        """
        return "\n".join(block.rendered for block in self.evidence_blocks(extracted))

    def evidence_blocks(
        self, extracted: Mapping[str, ArtifactText] | None = None
    ) -> list[EvidenceBlock]:
        """The blocks `evidence()` joins, in order, each with its location."""
        texts = extracted or {}
        blocks: list[EvidenceBlock] = []
        for step, call in self.tool_calls():
            blocks.append(
                EvidenceBlock(
                    location=f"steps[{step}].tool_call.output",
                    text=call.output,
                    rendered=evidence_block(step, call.name, call.arguments, call.output),
                )
            )
            for index, artifact in enumerate(call.artifacts):
                location = f"steps[{step}].tool_call.artifacts[{index}]"
                blocks.extend(_artifact_blocks(artifact, location, call.name, texts))
        for index, artifact in enumerate(self.artifacts):
            blocks.extend(_artifact_blocks(artifact, f"artifacts[{index}]", None, texts))
        return blocks

    def has_evidence(self) -> bool:
        return bool(self.artifacts) or any(s.tool_call is not None for s in self.steps)

    def tool_calls(self) -> list[IndexedToolCall]:
        """Every tool call paired with the index of the step that made it."""
        return [
            IndexedToolCall(step=i, call=s.tool_call)
            for i, s in enumerate(self.steps)
            if s.tool_call is not None
        ]

    def untrusted_text_segments(self) -> list[TextSegment]:
        """Return directly available text. Binary artifact extraction is a later stage."""
        segments: list[TextSegment] = []
        for idx, tc in self.tool_calls():
            if tc.output:
                segments.append(
                    TextSegment(
                        text=tc.output,
                        location=f"steps[{idx}].tool_call.output",
                        source_kind="tool_output",
                        subject=tc.name,
                        step=idx,
                    )
                )
            for artifact_idx, artifact in enumerate(tc.artifacts):
                if artifact.text is not None:
                    segments.append(
                        _artifact_segment(
                            artifact, f"steps[{idx}].tool_call.artifacts[{artifact_idx}]", idx
                        )
                    )
        for artifact_idx, artifact in enumerate(self.artifacts):
            if artifact.text is not None:
                segments.append(_artifact_segment(artifact, f"artifacts[{artifact_idx}]", None))
        return segments


def _artifact_blocks(
    artifact: Artifact, location: str, tool: str | None, extracted: Mapping[str, ArtifactText]
) -> list[EvidenceBlock]:
    if artifact.source == "user_upload":
        return []
    content = (
        ArtifactText(text=artifact.text) if artifact.text is not None else extracted.get(location)
    )
    if content is None:
        return []
    rendered = artifact_block(
        location,
        content.text,
        name=artifact.name,
        source=artifact.source,
        from_tool=tool,
        complete=content.complete,
    )
    return [EvidenceBlock(location=location, text=content.text, rendered=rendered)]


def _artifact_segment(artifact: Artifact, location: str, step: int | None) -> TextSegment:
    label = artifact.name or artifact.id or "artifact"
    return TextSegment(
        text=artifact.text or "",
        location=location,
        source_kind="artifact_text",
        subject=label,
        step=step,
        metadata={
            **artifact.metadata,
            "artifact_id": artifact.id,
            "media_type": artifact.media_type,
            "source": artifact.source,
            "sha256": artifact.sha256,
        },
    )
