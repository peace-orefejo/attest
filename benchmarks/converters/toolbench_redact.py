"""Redact contact details from ToolBench data: the vendored JSON and each converted run.

The same `redact` runs in both places: `toolbench_vendor.py` applies it to every string of the
upstream JSON before it is written under `benchmarks/sources/toolbench/`, and the converter
applies it again to each case (a no-op on the redacted inputs, kept as a second guard).
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import cast

from attest import Trajectory

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PHONE = re.compile(r"\+\d{1,3}(?:[ .-]?\d{2,4}){2,}")
# sha256 of each lowercased name of an individual named next to contact data upstream, kept
# hashed so this file doesn't republish it. The only one, an ATL Lines employee, is named in an
# email address, so the email rule already removes it; this rule catches it anywhere else.
NAME_SHA256 = frozenset({"b5271bcf284a0b4fe09030706cf971d1c90f6a34c3235172bef5f16d367894c5"})
WORD = re.compile(r"[^\W\d_]+")


def is_listed_name(word: str) -> bool:
    return hashlib.sha256(word.lower().encode("utf-8")).hexdigest() in NAME_SHA256


def redact(text: str, counts: Counter[str] | None = None) -> str:
    """Replace every email, phone number and listed name, counting replacements by kind."""
    found: Counter[str] = Counter()

    def name(match: re.Match[str]) -> str:
        if not is_listed_name(match.group()):
            return match.group()
        found["name"] += 1
        return "[name redacted]"

    text, found["email"] = EMAIL.subn("[email redacted]", text)
    text, found["phone"] = PHONE.subn("[phone redacted]", text)
    text = WORD.sub(name, text)
    if counts is not None:
        counts.update(+found)
    return text


def redact_value(value: object, counts: Counter[str] | None = None) -> object:
    """Redact every string, including dict keys, in a decoded JSON value."""
    if isinstance(value, str):
        return redact(value, counts)
    if isinstance(value, list):
        return [redact_value(item, counts) for item in cast(list[object], value)]
    if isinstance(value, dict):
        items = cast(dict[object, object], value).items()
        return {redact(str(key), counts): redact_value(item, counts) for key, item in items}
    return value


def redact_trajectory(trajectory: Trajectory) -> Trajectory:
    """Replace every email address, phone number and listed name in the run's text."""
    trajectory.task = redact(trajectory.task)
    trajectory.system_prompt = redact(trajectory.system_prompt or "") or None
    trajectory.final_answer = redact(trajectory.final_answer)
    for _, call in trajectory.tool_calls():
        call.output = redact(call.output)
        call.arguments = {key: redact_value(item) for key, item in call.arguments.items()}
    return trajectory
