"""CLI for attest: stats, tools, injection, role, run, demo, models."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import typer
from dotenv import load_dotenv
from pydantic import ValidationError

from ._llm import using
from .checks.judge_baseline import naive_judge
from .checks.injection import DEFAULT_DETECTORS, check_injection, load_regex_detector
from .checks.role import check_role_adherence
from .checks.tool_use import check_tool_use
from .checks.verify import extract_claims, judge_trajectory, verify_claims
from .providers import DEFAULT_PROVIDER, build_client, list_models, providers, resolve_key
from .results import CheckResult, Report, Severity
from .scoring.report import DEFAULT_CHECKS, evaluate, validate_evaluation_options
from .scoring.stats import wilson_interval
from .trajectory import Trajectory

load_dotenv()
app = typer.Typer(help="Evidence-grounded evaluation for AI agent trajectories.")

_PROVIDER_OPT = typer.Option(DEFAULT_PROVIDER, "--provider", "-p",
                             help="LLM provider: anthropic (default), openai, or gemini.")
_MODEL_OPT = typer.Option(None, "--model", "-m",
                          help="Model id; defaults to a sensible model for the provider.")


def _require_key(provider: str) -> None:
    if not resolve_key(provider):
        typer.echo(f"Set a {provider} API key (its env var) in the workspace .env to run this.")
        raise typer.Exit(code=1)


def _llm_ctx(provider: str, model: str | None):
    return using(build_client(provider, model))


def _load(path: Path) -> list[Trajectory]:
    try:
        raw = path.read_text().strip()
    except OSError as exc:
        raise typer.BadParameter(f"Could not read trajectory file {path}: {exc}") from exc
    if not raw:
        raise typer.BadParameter(f"Trajectory file {path} is empty.")

    lines = [(1, raw)] if path.suffix.lower() == ".json" else list(enumerate(raw.splitlines(), 1))
    trajectories: list[Trajectory] = []
    for line_number, line in lines:
        if not line.strip():
            continue
        try:
            trajectories.append(Trajectory.model_validate_json(line))
        except (ValidationError, ValueError) as exc:
            location = f"{path}" if path.suffix.lower() == ".json" else f"{path}, line {line_number}"
            detail = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
            raise typer.BadParameter(f"Invalid trajectory in {location}: {detail}") from exc
    return trajectories


def _emit_json(value) -> None:
    typer.echo(json.dumps(value, indent=2))


def _render_check(r: CheckResult, indent: str = "") -> None:
    score = f"{r.score:.0%}" if r.score is not None else "—"
    flag = "PASS" if r.passed else "FAIL"
    typer.echo(f"{indent}{r.check:13} {score:>4}  {flag}  {r.summary}")
    for f in r.findings:
        if f.severity is Severity.PASS:
            continue
        where = f" (step {f.step})" if f.step is not None else ""
        typer.echo(f"{indent}    {f.severity.value.upper()} {f.verdict}{where}: {f.subject}")
        if f.reason:
            typer.echo(f"{indent}      {f.reason}")


def _render_report(traj: Trajectory, report: Report) -> None:
    flag = "PASS" if report.passed else "FAIL"
    typer.echo(f"- {traj.task[:70]!r}")
    typer.echo(f"  {flag}  overall {report.overall_score:.0%}")
    for r in report.results:
        _render_check(r, indent="  ")
    typer.echo("")


@app.command()
def stats(successes: int, n: int) -> None:
    """Report a pass rate with a Wilson 95% confidence interval."""
    typer.echo(wilson_interval(successes, n).pct())


@app.command()
def tools(
    path: Path,
    appropriate: bool = typer.Option(False, "--appropriate",
                                      help="Also run the LLM tool-choice check (needs a key)."),
    provider: str = _PROVIDER_OPT,
    model: str = _MODEL_OPT,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Tool-use correctness only — deterministic, NO API key (unless --appropriate)."""
    if appropriate:
        _require_key(provider)
    ctx = _llm_ctx(provider, model) if appropriate else contextlib.nullcontext()
    with ctx:
        trajectories = _load(path)
        results = [(traj, check_tool_use(traj, appropriate=appropriate)) for traj in trajectories]
        if json_output:
            _emit_json([{"task": traj.task, "result": result.model_dump(mode="json")} for traj, result in results])
            return
        for traj, result in results:
            typer.echo(f"- {traj.task[:70]!r}")
            _render_check(result, indent="  ")
            typer.echo("")


@app.command()
def injection(
    path: Path,
    deep: bool = typer.Option(False, "--deep",
                              help="Also LLM-check whether the agent FOLLOWED each payload (needs a key)."),
    provider: str = _PROVIDER_OPT,
    model: str = _MODEL_OPT,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
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
        _require_key(provider)
    if patterns_only and patterns is None:
        raise typer.BadParameter("--patterns-only requires --patterns.", param_hint="--patterns-only")
    detectors = [] if patterns_only else list(DEFAULT_DETECTORS)
    if patterns is not None:
        try:
            detectors.append(load_regex_detector(patterns))
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--patterns") from exc
    ctx = _llm_ctx(provider, model) if deep else contextlib.nullcontext()
    with ctx:
        trajectories = _load(path)
        results = [
            (traj, check_injection(
                traj, deep=deep, detectors=detectors,
                extract_files=extract_files, allow_paths=allow_paths,
            ))
            for traj in trajectories
        ]
        if json_output:
            _emit_json([{"task": traj.task, "result": result.model_dump(mode="json")} for traj, result in results])
            return
        for traj, result in results:
            typer.echo(f"- {traj.task[:70]!r}")
            _render_check(result, indent="  ")
            typer.echo("")


@app.command()
def role(
    path: Path,
    provider: str = _PROVIDER_OPT,
    model: str = _MODEL_OPT,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Judge whether the agent stayed within its system-prompt-defined role (needs a key)."""
    _require_key(provider)
    with _llm_ctx(provider, model):
        trajectories = _load(path)
        results = [(traj, check_role_adherence(traj)) for traj in trajectories]
        if json_output:
            _emit_json([{"task": traj.task, "result": result.model_dump(mode="json")} for traj, result in results])
            return
        for traj, result in results:
            typer.echo(f"- {traj.task[:70]!r}")
            _render_check(result, indent="  ")
            typer.echo("")


@app.command()
def run(
    path: Path,
    checks: str = typer.Option(",".join(DEFAULT_CHECKS), "--checks",
                               help="Comma-separated: faithfulness,tool_use,injection,role."),
    appropriate: bool = typer.Option(False, "--appropriate",
                                     help="Also run the LLM tool-choice check (1 call per tool call)."),
    kind: str = typer.Option("factual", "--kind",
                             help="Answer type: 'factual' (default) or 'plan' (judge fidelity to the plan)."),
    provider: str = _PROVIDER_OPT,
    model: str = _MODEL_OPT,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Full report on a trajectory (or JSONL): runs the chosen checks + an overall score."""
    selected = [c.strip() for c in checks.split(",") if c.strip()]
    try:
        validate_evaluation_options(selected, kind)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _require_key(provider)
    trajectories = _load(path)
    if not json_output:
        typer.echo(f"Loaded {len(trajectories)} trajectory(ies) from {path}\n")

    overalls: list[float] = []
    reports: list[tuple[Trajectory, Report]] = []
    with _llm_ctx(provider, model):
        for traj in trajectories:
            report = evaluate(traj, checks=selected, appropriate=appropriate, answer_kind=kind)
            reports.append((traj, report))
            if not json_output:
                _render_report(traj, report)
            overalls.append(report.overall_score)

    if json_output:
        _emit_json({
            "trajectories": [
                {"task": traj.task, "report": report.model_dump(mode="json")}
                for traj, report in reports
            ],
            "mean_overall_score": sum(overalls) / len(overalls) if overalls else None,
        })
        return
    if overalls:
        typer.echo(f"Mean overall score: {sum(overalls) / len(overalls):.0%}")


@app.command()
def demo(
    path: Path = typer.Argument(Path("examples/trajectory.json")),
    provider: str = _PROVIDER_OPT,
    model: str = _MODEL_OPT,
) -> None:
    """Run the naive LLM-judge and attest side by side — the headline comparison."""
    _require_key(provider)
    with _llm_ctx(provider, model):
        for traj in _load(path):
            typer.echo("-" * 72)
            typer.echo(f"TASK: {traj.task}\n")
            typer.echo("Agent's answer (the initial LLM's claim):")
            typer.echo(f"  {traj.final_answer}\n")

            verdict = naive_judge(traj)
            typer.echo("Naive LLM-judge (reads the agent's reasoning):")
            typer.echo(f"  {'PASS' if verdict.passed else 'FAIL'} - {verdict.reason}\n")

            result = judge_trajectory(traj, extract_claims, verify_claims)
            typer.echo("attest (checks claims against real tool outputs only):")
            typer.echo(f"  grounding {result.score:.0%}  ({result.summary})")
            flagged = result.failures
            for f in flagged:
                typer.echo(f"    UNSUPPORTED: {f.subject}")
                if f.reason:
                    typer.echo(f"      {f.reason}")

            typer.echo("")
            if verdict.passed and flagged:
                typer.echo("=> attest caught a false claim the LLM-judge waved through.")
            elif not verdict.passed and flagged:
                typer.echo("=> both caught the problem.")
            elif verdict.passed and not flagged:
                typer.echo("=> both agree this answer is sound.")
            else:
                typer.echo("=> the LLM-judge flagged something attest's grounding didn't.")
    typer.echo("-" * 72)


@app.command()
def models(
    provider: str = typer.Argument(..., help=f"One of: {', '.join(providers())}."),
) -> None:
    """List a provider's models — live if its key is set, otherwise the curated shortlist."""
    source = "live" if resolve_key(provider) else "curated"
    typer.echo(f"{provider} models ({source}):")
    for name in list_models(provider):
        typer.echo(f"  {name}")


if __name__ == "__main__":
    app()
