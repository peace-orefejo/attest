"""Artifact display helpers."""

from __future__ import annotations

from ..content import Artifact


def artifact_subject(artifact: Artifact) -> str:
    return artifact.name or artifact.id or "artifact"
