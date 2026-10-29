"""Single-check commands: tools, injection and role."""

from __future__ import annotations

import contextlib
from pathlib import Path

import typer

from ...checks.injection import DEFAULT_DETECTORS, check_injection, load_regex_detector
from ...checks.role import check_role_adherence
from ...checks.tool_use import check_tool_use
from ...core import CheckResult, Trajectory
from ..app import JSON_OPT, MODEL_OPT, PROVIDER_OPT, app
from ..common import emit_json, llm_ctx, load_trajectories, print_results, require_key


def _emit(results: list[tuple[Trajectory, CheckResult]], json_output: bool) -> None:
    if json_output:
        emit_json([{"task": traj.task, "result": result.model_dump(mode="json")} for traj, result in results])
        return
    print_results([(traj.task, result) for traj, result in results])


@app.command()
def tools(
    path: Path,
    appropriate: bool = typer.Option(False, "--appropriate",
                                      help="Also run the LLM tool-choice check (needs a key)."),
    provider: str = PROVIDER_OPT,
    model: str = MODEL_OPT,
    json_output: bool = JSON_OPT,
) -> None:
    """Tool-use correctness only — deterministic, NO API key (unless --appropriate)."""
    if appropriate:
        require_key(provider)
    ctx = llm_ctx(provider, model) if appropriate else contextlib.nullcontext()
    with ctx:
        trajectories = load_trajectories(path)
        results = [(traj, check_tool_use(traj, appropriate=appropriate)) for traj in trajectories]
    _emit(results, json_output)


@app.command()
def injection(
    path: Path,
    deep: bool = typer.Option(False, "--deep",
                              help="Also LLM-check whether the agent FOLLOWED each payload (needs a key)."),
    provider: str = PROVIDER_OPT,
    model: str = MODEL_OPT,
    json_output: bool = JSON_OPT,
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
        True, "--extract-files/--no-extract-files",
        help="Extract supported embedded files before scanning.",
    ),
) -> None:
    """Flag prompt-injection payloads in tool outputs — deterministic, NO API key (unless --deep)."""
    if deep:
        require_key(provider)
    if patterns_only and patterns is None:
        raise typer.BadParameter("--patterns-only requires --patterns.", param_hint="--patterns-only")
    detectors = [] if patterns_only else list(DEFAULT_DETECTORS)
    if patterns is not None:
        try:
            detectors.append(load_regex_detector(patterns))
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--patterns") from exc
    ctx = llm_ctx(provider, model) if deep else contextlib.nullcontext()
    with ctx:
        trajectories = load_trajectories(path)
        results = [
            (traj, check_injection(
                traj, deep=deep, detectors=detectors,
                extract_files=extract_files, allow_paths=allow_paths,
            ))
            for traj in trajectories
        ]
    _emit(results, json_output)


@app.command()
def role(
    path: Path,
    provider: str = PROVIDER_OPT,
    model: str = MODEL_OPT,
    json_output: bool = JSON_OPT,
) -> None:
    """Judge whether the agent stayed within its system-prompt-defined role (needs a key)."""
    require_key(provider)
    with llm_ctx(provider, model):
        trajectories = load_trajectories(path)
        results = [(traj, check_role_adherence(traj)) for traj in trajectories]
    _emit(results, json_output)
