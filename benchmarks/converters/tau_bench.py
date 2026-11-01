"""Convert vendored τ-bench historical trajectories into benchmark cases.

    uv run python benchmarks/converters/tau_bench.py               # regenerate the case files
    uv run python benchmarks/converters/tau_bench.py --vendor DIR  # re-trim from a tau-bench clone

The cases come from the runs listed in `tau_bench_selection.py`, read from the trimmed copies
under `benchmarks/sources/tau-bench/`. Regenerating is deterministic: the same inputs give
byte-identical case files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

# isort: split
from tau_bench_selection import CASES, CaseSpec

ORIGIN = "tau-bench"
BENCHMARKS_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = BENCHMARKS_DIR / "sources" / ORIGIN
DATASETS_DIR = BENCHMARKS_DIR / "datasets"
UPSTREAM_TRAJECTORIES = "historical_trajectories"
STOP_TOKEN = "###STOP###"
DRAFT_PREFIX = "DRAFT label by the converter author; "

Domain = Literal["airline", "retail"]
Split = Literal["dev", "validation", "heldout"]

TOOLS: dict[Domain, list[str]] = {
    "airline": [
        "book_reservation",
        "calculate",
        "cancel_reservation",
        "get_reservation_details",
        "get_user_details",
        "list_all_airports",
        "search_direct_flight",
        "search_onestop_flight",
        "send_certificate",
        "think",
        "transfer_to_human_agents",
        "update_reservation_baggages",
        "update_reservation_flights",
        "update_reservation_passengers",
    ],
    "retail": [
        "calculate",
        "cancel_pending_order",
        "exchange_delivered_order_items",
        "find_user_id_by_email",
        "find_user_id_by_name_zip",
        "get_order_details",
        "get_product_details",
        "get_user_details",
        "list_all_product_types",
        "modify_pending_order_address",
        "modify_pending_order_items",
        "modify_pending_order_payment",
        "modify_user_address",
        "return_delivered_order_items",
        "think",
        "transfer_to_human_agents",
    ],
}
"""Each domain's tools, as named in upstream `tau_bench/envs/<domain>/tools/*.py`."""


class _Upstream(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FunctionCall(_Upstream):
    name: str
    arguments: str


class ToolCallMessage(_Upstream):
    id: str
    type: str
    function: FunctionCall


class Message(_Upstream):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCallMessage] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class Run(_Upstream):
    """One vendored run: the upstream entry with `reward` and `info` removed."""

    task_id: int
    trial: int
    traj: list[Message]


def domain_of(upstream_file: str) -> Domain:
    return "airline" if upstream_file.endswith("-airline.json") else "retail"


def task_family(domain: Domain, task_id: int) -> str:
    if domain == "retail":
        return f"{ORIGIN}/retail"
    if 0 <= task_id <= 24:
        return f"{ORIGIN}/airline-0-24"
    if 25 <= task_id <= 49:
        return f"{ORIGIN}/airline-25-49"
    raise ValueError(f"airline task {task_id} is outside the pilot's task families")


SPLIT_OF_FAMILY: dict[str, Split] = {
    f"{ORIGIN}/retail": "dev",
    f"{ORIGIN}/airline-0-24": "validation",
    f"{ORIGIN}/airline-25-49": "heldout",
}


def load_runs(upstream_file: str, source_dir: Path = SOURCE_DIR) -> list[Run]:
    path = source_dir / UPSTREAM_TRAJECTORIES / upstream_file
    raw: list[object] = json.loads(path.read_text(encoding="utf-8"))
    return [Run.model_validate(entry) for entry in raw]


def find_run(runs: list[Run], spec: CaseSpec) -> Run:
    matches = [run for run in runs if (run.task_id, run.trial) == (spec.task_id, spec.trial)]
    if len(matches) != 1:
        raise ValueError(f"{spec.id}: expected one run for task {spec.task_id} trial {spec.trial}")
    return matches[0]


def user_text(message: Message) -> str:
    return (message.content or "").replace(STOP_TOKEN, "").strip()


def task_text(traj: list[Message], later_turns: tuple[int, ...]) -> str:
    users = [index for index, message in enumerate(traj) if message.role == "user"]
    for index in later_turns:
        if index not in users[1:]:
            raise ValueError(f"turn {index} is not a later user turn")
    parts = [user_text(traj[users[0]])]
    parts.extend(f"Later the user said: {user_text(traj[index])}" for index in later_turns)
    return "\n\n".join(parts)


def tool_output(traj: list[Message], after: int, call_id: str) -> str:
    """The first tool message answering `call_id` after the call. Upstream reuses some call
    ids within a run, so outputs are matched by position as well as id."""
    for message in traj[after + 1 :]:
        if message.role == "tool" and message.tool_call_id == call_id:
            return message.content or ""
    raise ValueError(f"tool call {call_id} has no recorded output")


def steps(traj: list[Message]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for index, message in enumerate(traj):
        for position, call in enumerate(message.tool_calls or []):
            step: dict[str, object] = {}
            if position == 0 and message.content:
                step["thought"] = message.content
            arguments: dict[str, object] = json.loads(call.function.arguments)
            step["tool_call"] = {
                "name": call.function.name,
                "arguments": arguments,
                "output": tool_output(traj, index, call.id),
            }
            result.append(step)
    return result


def final_answer(traj: list[Message]) -> str:
    texts = [m.content for m in traj if m.role == "assistant" and m.content and not m.tool_calls]
    if not texts:
        raise ValueError("run has no assistant message to the user")
    return texts[-1]


def trajectory(run: Run, spec: CaseSpec, domain: Domain) -> dict[str, object]:
    system = [m.content for m in run.traj if m.role == "system" and m.content]
    return {
        "task": task_text(run.traj, spec.later_user_turns),
        "system_prompt": system[0],
        "allowed_tools": TOOLS[domain],
        "steps": steps(run.traj),
        "final_answer": final_answer(run.traj),
    }


def build_case(spec: CaseSpec, source_dir: Path = SOURCE_DIR) -> tuple[Split, dict[str, object]]:
    domain = domain_of(spec.upstream_file)
    family = task_family(domain, spec.task_id)
    run = find_run(load_runs(spec.upstream_file, source_dir), spec)
    case: dict[str, object] = {
        "id": spec.id,
        "check": spec.check,
        "category": spec.category,
        "source": "community",
        "origin": ORIGIN,
        "task_family": family,
        "origin_ref": f"{UPSTREAM_TRAJECTORIES}/{spec.upstream_file}#{spec.upstream_index}",
        "label_status": "draft",
        "annotators": [],
        "trajectory": trajectory(run, spec, domain),
        "expected": spec.expected,
        "notes": DRAFT_PREFIX + spec.notes,
    }
    return SPLIT_OF_FAMILY[family], case


def case_files(source_dir: Path = SOURCE_DIR) -> dict[str, str]:
    """Every case file this converter owns, relative to the datasets folder, with its text."""
    lines: dict[str, list[str]] = {}
    for spec in sorted(CASES, key=lambda s: s.id):
        split, case = build_case(spec, source_dir)
        name = f"{spec.check}/{split}-{ORIGIN}.jsonl"
        lines.setdefault(name, []).append(json.dumps(case, ensure_ascii=False))
    return {name: "\n".join(rows) + "\n" for name, rows in sorted(lines.items())}


def write_cases(datasets_dir: Path = DATASETS_DIR, source_dir: Path = SOURCE_DIR) -> list[Path]:
    written: list[Path] = []
    for name, text in case_files(source_dir).items():
        path = datasets_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def selected_indices(entries: list[dict[str, object]], upstream_file: str) -> list[int]:
    """The upstream positions of the selected runs, checked against their task and trial."""
    indices: set[int] = set()
    for spec in CASES:
        if spec.upstream_file != upstream_file:
            continue
        entry = entries[spec.upstream_index]
        if (entry["task_id"], entry["trial"]) != (spec.task_id, spec.trial):
            raise ValueError(f"{spec.id}: upstream index {spec.upstream_index} is another run")
        indices.add(spec.upstream_index)
    return sorted(indices)


def vendor(upstream_dir: Path, source_dir: Path = SOURCE_DIR) -> list[Path]:
    """Copy only the selected runs from an upstream clone, dropping `reward` and `info`."""
    written: list[Path] = []
    for upstream_file in sorted({spec.upstream_file for spec in CASES}):
        path = upstream_dir / UPSTREAM_TRAJECTORIES / upstream_file
        entries: list[dict[str, object]] = json.loads(path.read_text(encoding="utf-8"))
        kept = [
            {key: entries[index][key] for key in ("task_id", "trial", "traj")}
            for index in selected_indices(entries, upstream_file)
        ]
        target = source_dir / UPSTREAM_TRAJECTORIES / upstream_file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Convert vendored τ-bench runs into cases.")
    parser.add_argument("--vendor", type=Path, help="an upstream tau-bench clone to trim from")
    args = parser.parse_args(argv)
    upstream: Path | None = args.vendor
    paths = vendor(upstream) if upstream is not None else write_cases()
    for path in paths:
        print(path.relative_to(BENCHMARKS_DIR.parent))


if __name__ == "__main__":
    main()
