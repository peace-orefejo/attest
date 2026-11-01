"""Convert a vendored subset of AgentDojo runs into benchmark cases.

AgentDojo (https://github.com/ethz-spylab/agentdojo, MIT) records one JSON file per agent run:
the system prompt, the single user request, every tool call with the tool's output (some
outputs carry injected instructions), and the agent's final answer. The runs used here are
vendored under `benchmarks/sources/agentdojo/` with their `utility` and `security` results
stripped; see `SOURCE.md` there for the upstream commit, paths and hashes.

Run it from the repository root to regenerate the case files:

    uv run python benchmarks/converters/agentdojo.py

`--vendor DIR` re-creates the vendored inputs from a local mirror of the upstream files at the
pinned commit (same relative paths), stripping the evaluation fields.

The labels (in `agentdojo_selections.py`) are DRAFT labels written by hand by the converter
author, following `benchmarks/annotations/guidelines.md`. They never come from AgentDojo's own
results.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import cast

from agentdojo_runs import (
    BENCHMARKS_DIR,
    DATASETS_DIR,
    KEPT_RUN_FIELDS,
    ORIGIN,
    PIPELINE,
    SOURCE_DIR,
    UPSTREAM_COMMIT,
    as_object,
    read_json_object,
    strip_run,
    suite_tools,
    trajectory,
)
from agentdojo_selections import SELECTIONS, SPLIT_BY_SUITE, Selection

__all__ = [
    "DATASETS_DIR",
    "KEPT_RUN_FIELDS",
    "ORIGIN",
    "SELECTIONS",
    "SOURCE_DIR",
    "SPLIT_BY_SUITE",
    "UPSTREAM_COMMIT",
    "Selection",
    "build_case",
    "build_cases",
    "strip_run",
    "suite_tools",
    "write_cases",
]

DRAFT = "DRAFT label by the converter author;"
FOLDING = (
    "AgentDojo runs are single-turn: the task is the only user message, steps are the "
    "assistant's tool calls in order with each tool's recorded output (a call AgentDojo marks "
    "with an error shows that error text and is_error), allowed_tools is the suite's full "
    "tool list, and the final answer is the last assistant message. AgentDojo's utility and "
    "security results were stripped and not used."
)
NEEDS_APPROPRIATE = (
    "Scoring: attest predicts `incorrect` only when the runner is given --appropriate (and a "
    "model, since the tool-choice question isn't answered offline). Without it the off-task "
    "call comes back `correct` and counts as a missed violation."
)


def _expected_calls(selection: Selection, steps: list[dict[str, object]]) -> dict[str, object]:
    if any(index >= len(steps) for index in selection.off_task_calls):
        raise ValueError(f"{selection.case_id}: off-task step beyond the last call")
    calls: list[dict[str, object]] = []
    for index, step in enumerate(steps):
        name = as_object(step["tool_call"], "tool_call")["name"]
        expected_name = selection.off_task_calls.get(index)
        if expected_name is not None and expected_name != name:
            raise ValueError(
                f"{selection.case_id}: step {index} is {name!r}, not {expected_name!r}"
            )
        verdict = "correct" if expected_name is None else "incorrect"
        calls.append({"step": index, "verdict": verdict})
    return {"calls": calls}


def _expected(selection: Selection, steps: list[dict[str, object]]) -> dict[str, object]:
    if selection.check == "prompt_injection":
        return {"label": selection.injection_label}
    if selection.check == "tool_use":
        return _expected_calls(selection, steps)
    raise ValueError(f"{selection.case_id}: unsupported check {selection.check!r}")


def _notes(selection: Selection) -> str:
    injection = (
        f", injection_task_{selection.injection_task}"
        if selection.injection_task is not None
        else ""
    )
    provenance = (
        f"Run: AgentDojo {PIPELINE}, suite {selection.suite}, user_task_{selection.user_task}, "
        f"attack {selection.attack or 'none'}{injection}."
    )
    parts = [DRAFT, selection.reason]
    if selection.off_task_calls:
        parts.append(NEEDS_APPROPRIATE)
    parts += [provenance, FOLDING]
    return " ".join(parts)


def build_case(selection: Selection, root: Path = SOURCE_DIR) -> dict[str, object]:
    run = read_json_object(root / selection.upstream_path)
    if run.get("suite_name") != selection.suite or run.get("pipeline_name") != PIPELINE:
        raise ValueError(f"{selection.upstream_path}: suite or pipeline doesn't match")
    traj = trajectory(run, suite_tools(selection.suite, root))
    steps = cast(list[dict[str, object]], traj["steps"])
    return {
        "id": selection.case_id,
        "check": selection.check,
        "category": selection.category,
        "source": "community",
        "label_status": "draft",
        "annotators": [],
        "origin": ORIGIN,
        "task_family": f"{ORIGIN}/{selection.suite}",
        "origin_ref": selection.upstream_path,
        "trajectory": traj,
        "expected": _expected(selection, steps),
        "notes": _notes(selection),
    }


def build_cases(root: Path = SOURCE_DIR) -> dict[tuple[str, str], list[dict[str, object]]]:
    """Every case, grouped by (check, split) and sorted by id."""
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for selection in SELECTIONS:
        key = (selection.check, SPLIT_BY_SUITE[selection.suite])
        grouped.setdefault(key, []).append(build_case(selection, root))
    for cases in grouped.values():
        cases.sort(key=lambda case: str(case["id"]))
    return dict(sorted(grouped.items()))


def write_cases(root: Path = SOURCE_DIR, datasets: Path = DATASETS_DIR) -> list[Path]:
    written: list[Path] = []
    for (check, split), cases in build_cases(root).items():
        path = datasets / check / f"{split}-{ORIGIN}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def vendor(upstream: Path, root: Path = SOURCE_DIR) -> None:
    """Re-create the vendored inputs from a local mirror of the upstream files."""
    shutil.copyfile(upstream / "LICENSE", root / "LICENSE")
    for suite in SPLIT_BY_SUITE:
        source = upstream / "src/agentdojo/default_suites/v1" / suite / "task_suite.py"
        dest = root / "suites" / suite / "task_suite.py.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    for selection in SELECTIONS:
        run = read_json_object(upstream / selection.upstream_path)
        dest = root / selection.upstream_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(strip_run(run), indent=4, ensure_ascii=False) + "\n"
        dest.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--vendor",
        type=Path,
        metavar="UPSTREAM_DIR",
        help="first re-create the vendored inputs from this local mirror of the upstream files",
    )
    args = parser.parse_args(argv)
    upstream = cast(Path | None, args.vendor)
    if upstream is not None:
        vendor(upstream)
    for path in write_cases():
        print(path.relative_to(BENCHMARKS_DIR.parent))


if __name__ == "__main__":
    main()
