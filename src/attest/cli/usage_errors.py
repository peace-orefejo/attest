"""Print a usage error, such as a bad option value, as the JSON error envelope."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

import typer
from typer.core import TyperGroup

from .json_output import EXIT_INVALID_INPUT, fail

if TYPE_CHECKING:
    from typer._click.core import Context
    from typer._click.exceptions import UsageError
else:  # Typer only vendors Click in recent releases, so reach UsageError through BadParameter.
    UsageError = typer.BadParameter.__base__

PROGRAM = "attest"


class JsonUsageGroup(TyperGroup):
    """The `attest` command group. A usage error, raised before any command body runs, prints
    an `invalid_input` error envelope on stdout and exits 2 instead of Click's usage box."""

    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: Context | None = None,
        **extra: object,
    ) -> Context:
        try:
            return super().make_context(info_name, args, parent=parent, **extra)
        except UsageError as exc:
            _fail_usage(exc)

    def invoke(self, ctx: Context) -> object:
        try:
            return super().invoke(ctx)
        except UsageError as exc:
            _fail_usage(exc)


def _fail_usage(exc: UsageError) -> NoReturn:
    fail(_command_name(exc), "invalid_input", exc.format_message(), EXIT_INVALID_INPUT)


def _command_name(exc: UsageError) -> str:
    ctx = exc.ctx
    if ctx is None or ctx.parent is None or ctx.info_name is None:
        return PROGRAM
    return ctx.info_name
