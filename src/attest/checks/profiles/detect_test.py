"""The deterministic auto-mode detector: code evidence versus plain factual evidence."""

import time

import pytest

from attest import Artifact
from attest.checks.profiles import detect
from attest.checks.profiles.detect import detect_answer_kind
from attest.trajectory import Step, ToolCall, Trajectory

DIFF = (
    "diff --git a/app/session.py b/app/session.py\n"
    "--- a/app/session.py\n"
    "+++ b/app/session.py\n"
    "@@ -10,3 +10,3 @@ def expire():\n"
    "-    timeout = 600\n"
    "+    timeout = 900\n"
)

PYTHON_SOURCE = (
    "import os\n"
    "from typing import Any\n"
    "\n"
    "def load(path: str) -> Any:\n"
    "    return open(path).read()\n"
)

JSON_OUTPUT = '{\n  "city": "Paris",\n  "population": 2103000\n}\n{\n  "city": "Berlin"\n}\n'


def _traj(*calls: ToolCall) -> Trajectory:
    return Trajectory(task="t", steps=[Step(tool_call=c) for c in calls], final_answer="x")


def test_no_tool_calls_is_factual():
    detection = detect_answer_kind(_traj())
    assert detection.kind == "factual"
    assert "no tool calls" in detection.reason


def test_plain_web_evidence_is_factual():
    detection = detect_answer_kind(
        _traj(
            ToolCall(
                name="search",
                arguments={"query": "population of Paris"},
                output="Paris has 2,103,000 residents (2023 census).",
            ),
            ToolCall(
                name="fetch", arguments={"url": "https://example.com/cities"}, output=JSON_OUTPUT
            ),
        )
    )
    assert detection.kind == "factual"
    assert "2 tool call" in detection.reason


@pytest.mark.parametrize("tool", ["read_diff", "list_changed_files"])
def test_code_review_tool_names_resolve_to_code(tool):
    detection = detect_answer_kind(_traj(ToolCall(name=tool, output="")))
    assert detection.kind == "code"
    assert tool in detection.reason


def test_read_file_on_prose_is_not_enough():
    detection = detect_answer_kind(
        _traj(
            ToolCall(
                name="read_file",
                arguments={"path": "notes/report.md"},
                output="Revenue grew 12% in Q3.",
            )
        )
    )
    assert detection.kind == "factual"


def test_unified_diff_in_output_resolves_to_code():
    detection = detect_answer_kind(_traj(ToolCall(name="fetch", output=DIFF)))
    assert detection.kind == "code"
    assert "unified diff" in detection.reason


def test_bare_hunk_header_resolves_to_code():
    out = "@@ -1,2 +1,2 @@\n-a = 1\n+a = 2\n"
    assert detect_answer_kind(_traj(ToolCall(name="tool", output=out))).kind == "code"


@pytest.mark.parametrize(
    "arguments",
    [
        {"path": "src/attest/api.py"},
        {"file": "web/components/Button.tsx:42"},
        {"paths": ["README.md", "cmd/main.go"]},
        {"query": "grep timeout in lib/session.rb"},
        {"url": "https://github.com/org/repo/blob/main/src/lib.rs#L10"},
    ],
)
def test_source_file_in_arguments_resolves_to_code(arguments):
    detection = detect_answer_kind(_traj(ToolCall(name="read_file", arguments=arguments)))
    assert detection.kind == "code"
    assert "source file" in detection.reason


@pytest.mark.parametrize(
    "arguments",
    [
        {"path": "data/sales.csv"},
        {"url": "https://www.example.pl/news"},
        {"query": "python 3.11 release date"},
        {"note": "see e.g. the report"},
    ],
)
def test_non_source_arguments_do_not_resolve_to_code(arguments):
    detection = detect_answer_kind(_traj(ToolCall(name="lookup", arguments=arguments)))
    assert detection.kind == "factual"


def test_code_shaped_output_resolves_to_code():
    detection = detect_answer_kind(_traj(ToolCall(name="cat", output=PYTHON_SOURCE)))
    assert detection.kind == "code"
    assert "code-shaped" in detection.reason


def test_grep_style_numbered_code_lines_count():
    out = (
        "lib/a.js:3:import { x } from './x'\n"
        "lib/a.js:9:export function run(input) {\n"
        "lib/a.js:12:const limit = 10\n"
    )
    assert detect_answer_kind(_traj(ToolCall(name="search", output=out))).kind == "code"


def test_json_and_prose_are_not_code_shaped():
    prose = "Import duties rose.\nThe class of 2024 graduated.\nReturn policy applies.\n"
    detection = detect_answer_kind(
        _traj(ToolCall(name="fetch", output=JSON_OUTPUT), ToolCall(name="fetch", output=prose))
    )
    assert detection.kind == "factual"


def test_mixed_evidence_resolves_to_code():
    detection = detect_answer_kind(
        _traj(
            ToolCall(
                name="search", arguments={"query": "release notes"}, output="Version 2 shipped."
            ),
            ToolCall(name="fetch", output=DIFF),
        )
    )
    assert detection.kind == "code"
    assert "step 1" in detection.reason


def test_artifacts_are_ignored():
    traj = _traj(ToolCall(name="search", output="plain text"))
    traj.artifacts.append(Artifact(name="patch.diff", source="user_upload", text=DIFF))
    assert detect_answer_kind(traj).kind == "factual"


def test_detection_is_deterministic():
    traj = _traj(
        ToolCall(name="search", output="plain"),
        ToolCall(name="read_file", arguments={"path": "a.py"}, output=PYTHON_SOURCE),
    )
    results = {(d.kind, d.reason) for d in (detect_answer_kind(traj) for _ in range(5))}
    assert len(results) == 1


def test_detector_makes_no_model_calls():
    assert not hasattr(detect, "call")


def test_long_hostile_lines_are_scanned_in_bounded_time():
    hostile = ("if (" + ")" * 200_000 + "\n") * 50
    start = time.perf_counter()
    detection = detect_answer_kind(_traj(ToolCall(name="fetch", output=hostile)))
    assert detection.kind == "factual"
    assert time.perf_counter() - start < 2.0
