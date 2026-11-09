"""The Action's inputs, read from the environment `action.yml` sets."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel

DEFAULT_COMMAND = "/attest review"
DEFAULT_LABEL = "attest"
DEFAULT_GUIDELINES = "REVIEW.md"


class Settings(BaseModel):
    token: str
    api_key: str = ""
    provider: str = "anthropic"
    model: str | None = None
    reasoning: str = "auto"
    reviewer: str = ""
    """Login of the account that reviews when it is requested as a reviewer."""
    command: str = DEFAULT_COMMAND
    label: str = DEFAULT_LABEL
    guidelines: str = DEFAULT_GUIDELINES
    guidelines_set: bool = False
    """True when the workflow named a rules file, so a missing one is an error."""
    attestignore: bool = True
    fail_on_error: bool = False
    repository: str
    event_name: str
    event_path: Path
    api_url: str = "https://api.github.com"
    server_url: str = "https://github.com"
    summary_path: Path | None = None
    output_path: Path | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env

        def get(name: str, default: str = "") -> str:
            return env.get(name, default).strip()

        guidelines = get("ATTEST_GUIDELINES")
        model = get("ATTEST_MODEL")
        return cls(
            token=get("ATTEST_GITHUB_TOKEN") or get("GITHUB_TOKEN"),
            api_key=get("ATTEST_API_KEY"),
            provider=get("ATTEST_PROVIDER", "anthropic") or "anthropic",
            model=model or None,
            reasoning=get("ATTEST_REASONING", "auto") or "auto",
            reviewer=get("ATTEST_REVIEWER").removeprefix("@"),
            command=get("ATTEST_COMMAND") or DEFAULT_COMMAND,
            label=get("ATTEST_LABEL") or DEFAULT_LABEL,
            guidelines=guidelines or DEFAULT_GUIDELINES,
            guidelines_set=bool(guidelines),
            attestignore=_flag(get("ATTEST_ATTESTIGNORE", "true")),
            fail_on_error=_flag(get("ATTEST_FAIL_ON_ERROR", "false")),
            repository=get("GITHUB_REPOSITORY"),
            event_name=get("GITHUB_EVENT_NAME"),
            event_path=Path(get("GITHUB_EVENT_PATH")),
            api_url=get("GITHUB_API_URL") or "https://api.github.com",
            server_url=get("GITHUB_SERVER_URL") or "https://github.com",
            summary_path=Path(p) if (p := get("GITHUB_STEP_SUMMARY")) else None,
            output_path=Path(p) if (p := get("GITHUB_OUTPUT")) else None,
        )


def _flag(value: str) -> bool:
    return value.lower() in ("1", "true", "yes", "on")
