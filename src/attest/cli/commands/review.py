from __future__ import annotations

from pathlib import Path

import typer
from pydantic import BaseModel, ValidationError

from ...api import Attest
from ...code_review import PullRequest, ReviewGuidelines, ReviewOutput, load_guidelines
from ...code_review.gate.defaults import DEFAULT_MODES
from ...code_review.models import GATE_MODES, GateMode
from ...display import view
from ..context import require_key
from ..options import JSON_OPTION, MODEL_OPTION, PROVIDER_OPTION
from ..rendering import emit_json, print_view


class ReviewFile(BaseModel):
    pr: PullRequest
    outputs: list[ReviewOutput] | None = None


def review(
    path: Path = typer.Argument(
        ...,
        help='JSON file: {"pr": PullRequest, "outputs": [ReviewOutput, ...]}. '
        "Leave out outputs to have attest write the review.",
    ),
    guidelines: list[Path] = typer.Option(
        [],
        "--guidelines",
        "-g",
        help="Markdown file of review rules. Repeatable. Without one, attest uses its general "
        "standard.",
    ),
    follow: bool = typer.Option(
        True, "--follow/--no-follow", help="Drop outputs that break a review rule."
    ),
    mode: list[str] = typer.Option(
        [], "--mode", help="Override a gate mode, e.g. --mode issue=strict. Repeatable."
    ),
    deep: bool = typer.Option(
        True,
        "--deep/--no-deep",
        help="LLM-confirm injection hits and check whether outputs obeyed them.",
    ),
    provider: str = PROVIDER_OPTION,
    model: str | None = MODEL_OPTION,
    json_output: bool = JSON_OPTION,
) -> None:
    """Check each code review output against the diff and your review rules (needs a key)."""
    request = _load_review(path)
    modes = _parse_modes(mode)
    rules = _load_rules(guidelines)
    require_key(provider)
    try:
        result = Attest(provider=provider, model=model).review(
            request.pr,
            request.outputs,
            guidelines=rules,
            follow_guidelines=follow,
            modes=modes,
            deep=deep,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="PATH") from exc
    if json_output:
        emit_json(result.model_dump(mode="json"))
        return
    print_view(view(result))


def _load_review(path: Path) -> ReviewFile:
    try:
        raw = path.read_text()
    except OSError as exc:
        raise typer.BadParameter(f"Could not read review file {path}: {exc}") from exc
    try:
        return ReviewFile.model_validate_json(raw)
    except ValidationError as exc:
        error = exc.errors()[0]
        where = ".".join(str(part) for part in error["loc"]) or "file"
        raise typer.BadParameter(f"Invalid review file {path} at {where}: {error['msg']}") from exc


def _load_rules(paths: list[Path]) -> ReviewGuidelines:
    try:
        return load_guidelines(paths or None)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--guidelines") from exc


def _parse_modes(values: list[str]) -> dict[str, GateMode]:
    modes: dict[str, GateMode] = {}
    for value in values:
        output_type, sep, mode = value.partition("=")
        if not sep or output_type not in DEFAULT_MODES or mode not in GATE_MODES:
            raise typer.BadParameter(
                f"Expected TYPE=MODE with TYPE one of {', '.join(DEFAULT_MODES)} "
                f"and MODE one of {', '.join(GATE_MODES)}; got {value!r}.",
                param_hint="--mode",
            )
        modes[output_type] = "strict" if mode == "strict" else "lenient"
    return modes
