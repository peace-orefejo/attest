from __future__ import annotations

from functools import partial
from pathlib import Path

import typer

from ...checks.injection import (
    DEFAULT_DETECTORS,
    InjectionDetector,
    check_injection,
    load_regex_detector,
)
from ..context import llm_context, require_key
from ..json_output import json_command
from ..options import MODEL_OPTION, PROVIDER_OPTION
from ..single_check import run_single_check


@json_command("injection")
def injection(
    path: Path,
    deep: bool = typer.Option(
        False,
        "--deep",
        help="Also LLM-check whether the agent FOLLOWED each payload (needs a key).",
    ),
    provider: str = PROVIDER_OPTION,
    model: str | None = MODEL_OPTION,
    patterns: Path | None = typer.Option(
        None, "--patterns", help="JSON file containing additional named regex patterns."
    ),
    patterns_only: bool = typer.Option(
        False, "--patterns-only", help="Use --patterns instead of the built-in detectors."
    ),
    allow_paths: bool = typer.Option(
        False, "--allow-paths", help="Allow explicitly referenced local artifact paths."
    ),
    extract_files: bool = typer.Option(
        True,
        "--extract-files/--no-extract-files",
        help="Extract supported embedded files before scanning.",
    ),
) -> None:
    "Flag prompt-injection payloads in tool outputs — deterministic, NO API key (unless --deep)."
    if deep:
        require_key(provider)
    detectors = _detectors(patterns, patterns_only=patterns_only)
    with llm_context(provider, model, enabled=deep):
        check = partial(
            check_injection,
            deep=deep,
            detectors=detectors,
            extract_files=extract_files,
            allow_paths=allow_paths,
        )
        run_single_check("injection", path, check)


def _detectors(patterns: Path | None, *, patterns_only: bool) -> list[InjectionDetector]:
    if patterns is None:
        if patterns_only:
            raise typer.BadParameter(
                "--patterns-only requires --patterns.", param_hint="--patterns-only"
            )
        return list(DEFAULT_DETECTORS)
    base: list[InjectionDetector] = [] if patterns_only else list(DEFAULT_DETECTORS)
    return [*base, _custom_detector(patterns)]


def _custom_detector(patterns: Path) -> InjectionDetector:
    try:
        return load_regex_detector(patterns)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--patterns") from exc
