"""The Profile type and the answer-kind to profile lookup."""

from __future__ import annotations

from dataclasses import dataclass

from . import code, factual, plan

AUTO = "auto"


@dataclass(frozen=True)
class Profile:
    kind: str
    extract_prompt: str
    verify_prompt: str


_PROFILES: dict[str, Profile] = {
    module_kind: Profile(kind=module_kind, extract_prompt=module.EXTRACT_PROMPT,
                         verify_prompt=module.VERIFY_PROMPT)
    for module_kind, module in (("factual", factual), ("plan", plan), ("code", code))
}

PROFILE_KINDS: tuple[str, ...] = tuple(_PROFILES)
SUPPORTED_ANSWER_KINDS: tuple[str, ...] = (*PROFILE_KINDS, AUTO)


def get_profile(kind: str) -> Profile:
    """Return the prompts for one answer kind; "auto" must be resolved first."""
    profile = _PROFILES.get(kind)
    if profile is not None:
        return profile
    if kind == AUTO:
        raise ValueError('Answer kind "auto" must be resolved to a concrete kind first.')
    raise ValueError(
        f"Unknown answer kind {kind!r}. Choose from: {', '.join(PROFILE_KINDS)}."
    )
