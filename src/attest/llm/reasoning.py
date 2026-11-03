"""How much a judge model may reason before it answers: the levels and the per-check policy.

`"auto"` (the default) lets the provider's adaptive thinking decide at low effort, so an easy
claim gets little or no reasoning and a hard one gets more. `"off"` turns reasoning off where the
model allows it and otherwise uses its lowest level; `"low"`, `"medium"` and `"high"` set the
effort. What each level sends to each model is in `attest.llm.thinking`.

Reasoning tokens are billed as output and count against `max_tokens`, so every call that may
reason gets `answer_room`: the tokens its answer needs plus `REASONING_ALLOWANCE` for its level.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

Reasoning = Literal["auto", "off", "low", "medium", "high"]
REASONING_LEVELS: tuple[Reasoning, ...] = get_args(Reasoning)
DEFAULT_REASONING: Reasoning = "auto"

CALL_SITES: tuple[str, ...] = (
    "faithfulness.extract",
    "faithfulness.verify",
    "tool_use.appropriate",
    "tool_use.recovery",
    "injection.deep",
    "injection.confirm",
    "injection.effect",
    "role",
    "policy",
    "guidelines.check",
    "guidelines.confirm",
    "writer",
    "judge",
)
"""Every place attest calls a model. A policy key is one of these or the check before the dot."""

CHECKS: tuple[str, ...] = tuple(dict.fromkeys(site.split(".")[0] for site in CALL_SITES))

REASONING_ALLOWANCE: dict[Reasoning, int] = {
    "off": 0,
    "auto": 4096,
    "low": 4096,
    "medium": 8192,
    "high": 16384,
}
"""Output tokens added to `max_tokens` so reasoning at each level can't starve the answer."""

MAX_REQUEST_TOKENS = 20_000
"""Upper bound on `max_tokens` with the allowance: the Anthropic SDK refuses a non-streaming
request it expects to take over ten minutes (about 21,300 output tokens)."""


def answer_room(visible: int, level: Reasoning) -> int:
    """`max_tokens` for a call whose answer needs `visible` tokens and may reason at `level`."""
    return max(visible, min(visible + REASONING_ALLOWANCE[level], MAX_REQUEST_TOKENS))


class ReasoningPolicy(BaseModel):
    """The reasoning level of every judge call: `default`, overridden per check or call site.

    A key of `checks` is a check such as `"faithfulness"` or one call site such as
    `"faithfulness.verify"` (see `CALL_SITES`); the most specific key wins.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    default: Reasoning = DEFAULT_REASONING
    checks: dict[str, Reasoning] = Field(default_factory=dict[str, Reasoning])

    @field_validator("checks")
    @classmethod
    def _known_keys(cls, checks: dict[str, Reasoning]) -> dict[str, Reasoning]:
        unknown = sorted(set(checks) - {*CALL_SITES, *CHECKS})
        if unknown:
            raise ValueError(
                f"Unknown reasoning key(s): {', '.join(unknown)}. Use 'default', a check "
                f"({', '.join(CHECKS)}) or a call site ({', '.join(CALL_SITES)})."
            )
        return checks

    def level(self, site: str) -> Reasoning:
        """The level for one call site: its own key, else its check's, else the default."""
        check = site.split(".")[0]
        return self.checks.get(site) or self.checks.get(check) or self.default


ReasoningInput = Reasoning | Mapping[str, Reasoning] | ReasoningPolicy
"""A level for every call, a mapping of check or call site to level (with an optional
`"default"` key), or a `ReasoningPolicy`."""


def reasoning_policy(value: ReasoningInput) -> ReasoningPolicy:
    """Turn `Attest(reasoning=...)` into a policy; a bad level or key raises `ValueError`."""
    if isinstance(value, ReasoningPolicy):
        return value
    if isinstance(value, str):
        return ReasoningPolicy.model_validate({"default": value})
    overrides = dict(value)
    default = overrides.pop("default", DEFAULT_REASONING)
    return ReasoningPolicy.model_validate({"default": default, "checks": overrides})


def parse_reasoning(text: str) -> ReasoningPolicy:
    """Read `"medium"` or `"faithfulness=medium,default=auto"`; a bad one raises `ValueError`."""
    if "=" not in text:
        return ReasoningPolicy.model_validate({"default": text.strip()})
    pairs: dict[str, str] = {}
    for part in filter(None, (piece.strip() for piece in text.split(","))):
        key, sep, level = part.partition("=")
        if not sep:
            raise ValueError(f"Expected KEY=LEVEL, got {part!r}.")
        pairs[key.strip()] = level.strip()
    default = pairs.pop("default", DEFAULT_REASONING)
    return ReasoningPolicy.model_validate({"default": default, "checks": pairs})


def describe_reasoning(policy: ReasoningPolicy) -> str:
    """The policy in the `--reasoning` text form, such as `"auto"` or `"default=auto,role=high"`.

    Equivalent policies read the same: an override that sets the level its site would get
    anyway is left out, so `"default=auto,role=auto"` reads `"auto"`.
    """
    checks = normalized(policy).checks
    if not checks:
        return policy.default
    overrides = (f"{key}={level}" for key, level in sorted(checks.items()))
    return ",".join([f"default={policy.default}", *overrides])


def normalized(policy: ReasoningPolicy) -> ReasoningPolicy:
    """The same policy without overrides that change nothing."""
    checks: dict[str, Reasoning] = {
        k: v for k, v in policy.checks.items() if "." not in k and v != policy.default
    }
    parents = dict(checks)
    for site, level in policy.checks.items():
        if "." in site and level != parents.get(site.split(".")[0], policy.default):
            checks[site] = level
    return ReasoningPolicy(default=policy.default, checks=checks)
