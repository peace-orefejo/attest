"""The JSON every CLI command prints: one versioned envelope around each command's data."""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import Generic, Literal, ParamSpec, TypeVar

import typer
from pydantic import BaseModel, ConfigDict

from ..checks.judge_baseline import JudgeVerdict
from ..code_review import ReviewResult
from ..llm import ProviderConfigError, Usage
from ..results import CheckResult, Disposition
from ..scoring.stats import Proportion
from ..utils.failures import failure_reason
from .outcomes import TaskReport, TaskResult

SCHEMA_VERSION = "2"
SCHEMA_BASE_URL = f"https://peace-orefejo.github.io/attest/schemas/v{SCHEMA_VERSION}"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INVALID_INPUT = 2
EXIT_BUDGET_EXCEEDED = 3

ErrorCode = Literal["invalid_input", "missing_api_key", "provider_config", "command_failed"]
DemoOutcome = Literal["caught", "both_caught", "both_passed", "judge_only"]

DataT = TypeVar("DataT", bound=BaseModel)
P = ParamSpec("P")


class RunData(BaseModel):
    """`attest run`: one report per trajectory, plus totals for the whole file.

    `passed` counts runs whose verdict is `pass`; `checks_passed` counts runs whose checks all
    passed, including runs that still need review.
    """

    trajectories: list[TaskReport]
    total: int
    evaluated: int
    passed: int
    checks_passed: int
    verdicts: dict[Disposition, int]
    mean_overall_score: float | None
    usage: Usage
    budget_exceeded: str | None = None


class CheckData(BaseModel):
    """`attest tools`, `injection` and `role`: one check result per trajectory."""

    trajectories: list[TaskResult]


class DemoComparison(BaseModel):
    task: str
    answer: str
    judge: JudgeVerdict
    attest: CheckResult
    outcome: DemoOutcome


class DemoData(BaseModel):
    """`attest demo`: the naive LLM judge and attest side by side, per trajectory."""

    comparisons: list[DemoComparison]


class ModelList(BaseModel):
    """`attest models`: model ids for one provider."""

    provider: str
    source: Literal["live", "curated"]
    models: list[str]


class Output(BaseModel, Generic[DataT]):
    """A successful command. `data` holds the command's result."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    schema_version: Literal["2"] = "2"
    command: str
    ok: Literal[True] = True
    data: DataT


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str


class ErrorOutput(BaseModel):
    """A command that could not run. Printed on stdout like any other output."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    schema_version: Literal["2"] = "2"
    command: str
    ok: Literal[False] = False
    error: ErrorDetail


class CommandError(Exception):
    def __init__(self, code: ErrorCode, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.exit_code = exit_code


COMMAND_DATA: dict[str, type[BaseModel]] = {
    "run": RunData,
    "tools": CheckData,
    "injection": CheckData,
    "role": CheckData,
    "review": ReviewResult,
    "demo": DemoData,
    "stats": Proportion,
    "models": ModelList,
}


def emit(command: str, data: BaseModel) -> None:
    _print(Output[BaseModel](command=command, data=data))


def json_command(name: str) -> Callable[[Callable[P, None]], Callable[P, None]]:
    """Turn errors raised inside a command into a JSON error envelope on stdout.

    Bad input exits 2. Any other failure, such as a provider error a check doesn't absorb,
    is `command_failed` and exits 1.
    """

    def decorate(command: Callable[P, None]) -> Callable[P, None]:
        @functools.wraps(command)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> None:
            try:
                command(*args, **kwargs)
            except typer.BadParameter as exc:
                _fail(name, "invalid_input", _bad_parameter_message(exc), EXIT_INVALID_INPUT)
            except CommandError as exc:
                _fail(name, exc.code, str(exc), exc.exit_code)
            except (typer.Exit, typer.Abort):
                raise
            except ProviderConfigError as exc:
                _fail(name, "provider_config", str(exc), EXIT_ERROR)
            except Exception as exc:
                _fail(name, "command_failed", failure_reason("The command", exc), EXIT_ERROR)

        return wrapper

    return decorate


def schema_for(command: str) -> dict[str, object]:
    """The JSON Schema of a successful `command`'s output."""
    envelope = Output[COMMAND_DATA[command]]
    schema = envelope.model_json_schema(mode="serialization")
    properties = schema["properties"]
    assert isinstance(properties, dict)
    properties["command"] = {"const": command, "title": "Command", "type": "string"}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_BASE_URL}/{command}.json",
        **schema,
        "title": f"attest {command}",
    }


def error_schema() -> dict[str, object]:
    """The JSON Schema of the error envelope every command can print."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_BASE_URL}/error.json",
        **ErrorOutput.model_json_schema(mode="serialization"),
        "title": "attest error",
    }


def all_schemas() -> dict[str, dict[str, object]]:
    return {**{name: schema_for(name) for name in COMMAND_DATA}, "error": error_schema()}


def print_json(value: object) -> None:
    typer.echo(json.dumps(value, indent=2))


def _print(output: BaseModel) -> None:
    print_json(output.model_dump(mode="json", serialize_as_any=True))


def _fail(command: str, code: ErrorCode, message: str, exit_code: int) -> None:
    _print(ErrorOutput(command=command, error=ErrorDetail(code=code, message=message)))
    raise typer.Exit(code=exit_code)


def _bad_parameter_message(exc: typer.BadParameter) -> str:
    hint = exc.param_hint
    if isinstance(hint, str) and hint and not exc.message.startswith(hint):
        return f"{hint}: {exc.message}"
    return exc.message
