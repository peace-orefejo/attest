"""The data model for an agent run. Tool outputs are the evidence attest trusts."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .content import Artifact, TextSegment
from .utils import artifact_subject


class ToolCall(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)
    output: str = ""
    artifacts: list[Artifact] = Field(default_factory=list)


class Step(BaseModel):
    thought: str | None = None
    tool_call: ToolCall | None = None


class Trajectory(BaseModel):
    task: str
    system_prompt: str | None = None
    allowed_tools: list[str] | None = None
    steps: list[Step] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    final_answer: str

    def evidence(self) -> str:
        """The concatenated real tool outputs — the only text attest trusts."""
        blocks: list[str] = []
        for i, step in enumerate(self.steps):
            if step.tool_call is not None:
                tc = step.tool_call
                blocks.append(f"[{i}] {tc.name}({tc.arguments}) -> {tc.output}")
        return "\n".join(blocks)

    def has_evidence(self) -> bool:
        return bool(self.artifacts) or any(s.tool_call is not None for s in self.steps)

    def tool_calls(self) -> list[tuple[int, ToolCall]]:
        return [(i, s.tool_call) for i, s in enumerate(self.steps) if s.tool_call is not None]

    def untrusted_text_segments(self) -> list[TextSegment]:
        """Return directly available text. Binary artifact extraction is a later stage."""
        segments: list[TextSegment] = []
        for idx, tc in self.tool_calls():
            if tc.output:
                segments.append(TextSegment(
                    text=tc.output,
                    location=f"steps[{idx}].tool_call.output",
                    source_kind="tool_output",
                    subject=tc.name,
                    step=idx,
                ))
            for artifact_idx, artifact in enumerate(tc.artifacts):
                if artifact.text is not None:
                    segments.append(_artifact_segment(
                        artifact, f"steps[{idx}].tool_call.artifacts[{artifact_idx}]", idx
                    ))
        for artifact_idx, artifact in enumerate(self.artifacts):
            if artifact.text is not None:
                segments.append(_artifact_segment(artifact, f"artifacts[{artifact_idx}]", None))
        return segments


def _artifact_segment(artifact: Artifact, location: str, step: int | None) -> TextSegment:
    label = artifact_subject(artifact)
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
