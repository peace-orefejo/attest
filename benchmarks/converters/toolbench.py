"""Convert vendored ToolBench DFSDT answer samples into benchmark cases.

Run `uv run python benchmarks/converters/toolbench.py` to regenerate
`benchmarks/datasets/<check>/<split>-toolbench.jsonl` from `benchmarks/sources/toolbench/`.
With `--vendor` it first re-fetches and redacts those inputs (see `toolbench_vendor.py`).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel, Field

from attest import Trajectory
from toolbench_cases import SPECS, CaseSpec
from toolbench_redact import redact_trajectory
from toolbench_vendor import vendor

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "benchmarks" / "sources" / "toolbench"
DATASETS = ROOT / "benchmarks" / "datasets"
ORIGIN = "toolbench"
SPLIT_BY_GROUP = {"g1": "dev", "g2": "validation", "g3": "heldout"}
CHECK_SHORT = {"faithfulness": "faith", "tool_use": "tool", "recovery": "rec"}
DRAFT_PREFIX = "DRAFT label by the converter author; "
FINISH = "Finish"
TRUNCATION_MARK = "..."


class FunctionCall(BaseModel):
    name: str
    arguments: str = ""


class Message(BaseModel):
    role: str
    content: str | None = None
    name: str | None = None
    function_call: FunctionCall | None = None


class FunctionDef(BaseModel):
    name: str


class AnswerGeneration(BaseModel):
    query: str
    function: list[FunctionDef]
    train_messages: list[list[Message]] = Field(default_factory=list[list[Message]])


class AnswerFile(BaseModel):
    answer_generation: AnswerGeneration


class Observation(BaseModel):
    error: str
    response: str
    truncated: bool


def load_sample(relative: str) -> AnswerGeneration:
    text = (SOURCES / relative).read_text(encoding="utf-8")
    return AnswerFile.model_validate_json(text).answer_generation


def select_chain(sample: AnswerGeneration) -> list[Message]:
    """The last chain in `train_messages`: DFSDT stores one growing prefix per step, so the
    last one is the whole final path. It must end with a call to `Finish`."""
    if not sample.train_messages:
        raise ValueError("sample has no train_messages")
    chain = sample.train_messages[-1]
    last = chain[-1].function_call
    if last is None or last.name != FINISH:
        raise ValueError("the last chain does not end with Finish")
    return chain


def parse_observation(content: str) -> Observation:
    """Decode the outer JSON layer of a function message. ToolBench cuts long observations at
    1024 characters and appends '...', which leaves the outer JSON unterminated."""
    try:
        decoded = json.loads(content)
        return Observation(error=decoded["error"], response=decoded["response"], truncated=False)
    except json.JSONDecodeError:
        pass
    body = content.removesuffix(TRUNCATION_MARK)
    while body:
        try:
            decoded = json.loads(body + '"}')
            return Observation(error=decoded["error"], response=decoded["response"], truncated=True)
        except json.JSONDecodeError:
            body = body[:-1]
    raise ValueError(f"cannot decode observation: {content[:80]!r}")


def render_output(observation: Observation) -> str:
    response = observation.response + (TRUNCATION_MARK if observation.truncated else "")
    if observation.error:
        return f"error: {observation.error}\nresponse: {response}"
    return response


def finish_answer(call: FunctionCall) -> str:
    arguments = json.loads(call.arguments)
    if arguments.get("return_type") != "give_answer":
        return ""
    return str(arguments["final_answer"])


def build_trajectory(sample: AnswerGeneration) -> Trajectory:
    chain = select_chain(sample)
    steps: list[dict[str, object]] = []
    pending: dict[str, object] | None = None
    for message in chain:
        call = message.function_call
        if message.role == "assistant" and call is not None and call.name != FINISH:
            pending = {"name": call.name, "arguments": json.loads(call.arguments or "{}")}
            steps.append({"tool_call": pending})
        elif message.role == "function" and pending is not None:
            observation = parse_observation(message.content or "")
            pending["output"] = render_output(observation)
            if observation.error:
                pending["is_error"] = True
            pending = None
    finish = chain[-1].function_call
    assert finish is not None
    return Trajectory.model_validate(
        {
            "task": first_user_message(chain),
            "system_prompt": chain[0].content,
            "allowed_tools": [f.name for f in sample.function if f.name != FINISH],
            "steps": steps,
            "final_answer": finish_answer(finish),
        }
    )


def first_user_message(chain: list[Message]) -> str:
    user = next(m for m in chain if m.role == "user")
    return (user.content or "").strip().removesuffix("Begin!").strip()


def group_of(spec: CaseSpec) -> str:
    return spec.sample.split("/")[2].split("_")[0].lower()


def case_id(spec: CaseSpec) -> str:
    number = spec.sample.rsplit("/", 1)[1].split("_")[0]
    return f"{ORIGIN}-{group_of(spec)}-{number}-{CHECK_SHORT[spec.check]}"


def build_case(spec: CaseSpec) -> dict[str, object]:
    sample = load_sample(spec.sample)
    return {
        "id": case_id(spec),
        "check": spec.check,
        "category": spec.category,
        "source": "community",
        "origin": ORIGIN,
        "task_family": f"{ORIGIN}/{group_of(spec)}",
        "origin_ref": f"{spec.sample}#train_messages[{len(sample.train_messages) - 1}]",
        "label_status": "draft",
        "annotators": [],
        "trajectory": redact_trajectory(build_trajectory(sample)).model_dump(
            mode="json", exclude_defaults=True
        ),
        "expected": spec.expected,
        "notes": DRAFT_PREFIX + spec.notes,
    }


def build_all() -> dict[Path, list[dict[str, object]]]:
    files: dict[Path, list[dict[str, object]]] = {}
    for spec in SPECS:
        path = DATASETS / spec.check / f"{SPLIT_BY_GROUP[group_of(spec)]}-{ORIGIN}.jsonl"
        files.setdefault(path, []).append(build_case(spec))
    return files


def render(cases: list[dict[str, object]]) -> str:
    return "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Regenerate the ToolBench case files.")
    parser.add_argument("--vendor", action="store_true", help="re-fetch and redact the inputs")
    if parser.parse_args(argv).vendor:
        vendor(SOURCES)
    for path, cases in sorted(build_all().items()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(cases), encoding="utf-8")
        print(f"wrote {len(cases)} cases to {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
