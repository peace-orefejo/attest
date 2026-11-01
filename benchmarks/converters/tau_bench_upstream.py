"""τ-bench's upstream data as vendored here: where it lives, its message shape and tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

# isort: split
from tau_bench_spec import CaseSpec

ORIGIN = "tau-bench"
BENCHMARKS_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = BENCHMARKS_DIR / "sources" / ORIGIN
DATASETS_DIR = BENCHMARKS_DIR / "datasets"
UPSTREAM_TRAJECTORIES = "historical_trajectories"

Domain = Literal["airline", "retail"]

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


def load_runs(upstream_file: str, source_dir: Path = SOURCE_DIR) -> list[Run]:
    path = source_dir / UPSTREAM_TRAJECTORIES / upstream_file
    raw: list[object] = json.loads(path.read_text(encoding="utf-8"))
    return [Run.model_validate(entry) for entry in raw]


def find_run(runs: list[Run], spec: CaseSpec) -> Run:
    matches = [run for run in runs if (run.task_id, run.trial) == (spec.task_id, spec.trial)]
    if len(matches) != 1:
        raise ValueError(f"{spec.id}: expected one run for task {spec.task_id} trial {spec.trial}")
    return matches[0]
