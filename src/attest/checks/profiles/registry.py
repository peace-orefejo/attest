from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ...prompts.profiles import code, factual, plan

AUTO = "auto"


class Profile(BaseModel):
    """The extraction and verification prompts for one answer kind."""

    model_config = ConfigDict(frozen=True)

    kind: str
    extract_prompt: str
    verify_prompt: str


_PROFILES: dict[str, Profile] = {
    "factual": Profile(
        kind="factual", extract_prompt=factual.EXTRACT_PROMPT, verify_prompt=factual.VERIFY_PROMPT
    ),
    "plan": Profile(
        kind="plan", extract_prompt=plan.EXTRACT_PROMPT, verify_prompt=plan.VERIFY_PROMPT
    ),
    "code": Profile(
        kind="code", extract_prompt=code.EXTRACT_PROMPT, verify_prompt=code.VERIFY_PROMPT
    ),
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
    raise ValueError(f"Unknown answer kind {kind!r}. Choose from: {', '.join(PROFILE_KINDS)}.")
