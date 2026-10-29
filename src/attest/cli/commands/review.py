"""attest review: check every output of a code review and decide which to keep."""

from __future__ import annotations

from pathlib import Path

import typer
from pydantic import BaseModel, ValidationError

from ...api import Attest
from ...code_review import PullRequest, ReviewGuidelines, ReviewOutput, load_guidelines
from ...code_review.gate.defaults import DEFAULT_MODES, DROPPING_VERDICTS
from ...display import view
from ..app import JSON_OPT, MODEL_OPT, PROVIDER_OPT, app
from ..common import emit_json, print_view, read_text, require_key


class ReviewFile(BaseModel):
    pr: PullRequest
    outputs: list[ReviewOutput] | None = None


def load_review(path: Path) -> ReviewFile:
    raw = read_text(path, "review")
    try:
        return ReviewFile.model_validate_json(raw)
    except ValidationError as exc:
        error = exc.errors()[0]
        where = ".".join(str(part) for part in error["loc"]) or "file"
        raise typer.BadParameter(f"Invalid review file {path} at {where}: {error['msg']}") from exc


def load_rules(paths: list[Path]) -> ReviewGuidelines:
    try:
        return load_guidelines(paths or None)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--guidelines") from exc


def parse_modes(values: list[str]) -> dict[str, str]:
    modes: dict[str, str] = {}
    for value in values:
        output_type, sep, mode = value.partition("=")
        if not sep or output_type not in DEFAULT_MODES or mode not in DROPPING_VERDICTS:
            raise typer.BadParameter(
                f"Expected TYPE=MODE with TYPE one of {', '.join(DEFAULT_MODES)} "
                f"and MODE one of {', '.join(DROPPING_VERDICTS)}; got {value!r}.",
                param_hint="--mode",
            )
        modes[output_type] = mode
    return modes


@app.command()
def review(
    path: Path = typer.Argument(..., help='JSON file: {"pr": PullRequest, "outputs": [ReviewOutput, ...]}. '
                                          "Leave out outputs to have attest write the review."),
    guidelines: list[Path] = typer.Option([], "--guidelines", "-g",
                                          help="Markdown file of review rules. Repeatable. "
                                               "Without one, attest uses its general standard."),
    follow: bool = typer.Option(True, "--follow/--no-follow",
                                help="Drop outputs that break a review rule."),
    mode: list[str] = typer.Option([], "--mode",
                                   help="Override a gate mode, e.g. --mode issue=strict. Repeatable."),
    deep: bool = typer.Option(True, "--deep/--no-deep",
                              help="LLM-confirm injection hits and check whether outputs obeyed them."),
    provider: str = PROVIDER_OPT,
    model: str = MODEL_OPT,
    json_output: bool = JSON_OPT,
) -> None:
    """Check each code review output against the diff and your review rules, and decide which to keep (needs a key)."""
    request = load_review(path)
    modes = parse_modes(mode)
    rules = load_rules(guidelines)
    require_key(provider)
    try:
        result = Attest(provider=provider, model=model).review(
            request.pr, request.outputs, guidelines=rules, follow_guidelines=follow, modes=modes, deep=deep)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="PATH") from exc
    if json_output:
        emit_json(result.model_dump(mode="json"))
        return
    print_view(view(result))
