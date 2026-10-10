"""Shared builders for these tests."""

import base64

from attest import Artifact


def _artifact(data: bytes, name: str, media_type: str) -> Artifact:
    return Artifact(
        name=name, media_type=media_type,
        data_base64=base64.b64encode(data).decode(),
        source="user_upload",
    )


def _texts(outcome):
    return [(segment.source_kind, segment.text) for segment in outcome.segments]
