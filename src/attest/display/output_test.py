"""render(): every result type becomes a structured, aligned, plain-text view."""

import io
import re

import pytest
from rich.console import Console

from attest.display import render, show, view
from attest.results import CheckResult, Finding, Report, Severity

RLO = chr(0x202E)


def _faithfulness() -> CheckResult:
    return CheckResult(
        check="faithfulness",
        passed=False,
        score=0.5,
        summary="1/2 checkable claims grounded.",
        findings=[
            Finding(
                severity=Severity.FAIL,
                verdict="unsupported",
                subject="Paris is larger",
                reason="Berlin is larger.",
                evidence="Berlin population: 3,677,000",
            ),
            Finding(
                severity=Severity.PASS,
                verdict="supported",
                subject="Berlin has 3.7M",
                reason="hidden for passes",
            ),
        ],
    )


def test_report_has_a_header_a_summary_table_and_details():
    report = Report(
        results=[
            _faithfulness(),
            CheckResult(check="tool_use", passed=True, score=1.0, summary="ok"),
        ]
    )
    text = render(report, title="Which is larger?")
    lines = text.splitlines()
    assert lines[0].startswith("FAIL  Which is larger?")
    assert "overall 75% · 2 checks" in lines[1]
    assert any(
        line.split() == ["faithfulness", "50%", "FAIL", "1/2", "checkable", "claims", "grounded."]
        for line in lines
    )
    assert any(line.split()[:3] == ["tool_use", "100%", "PASS"] for line in lines)
    assert "✗  unsupported  Paris is larger" in text
    assert "evidence  Berlin population: 3,677,000" in text
    assert "✓  supported    Berlin has 3.7M" in text
    assert "hidden for passes" not in text


def test_check_result_without_a_score_says_nothing_about_score():
    text = render(
        CheckResult(check="injection", passed=True, summary="Nothing found."), title="task"
    )
    assert "score" not in text
    assert "injection · Nothing found." in text


def test_wrapped_reasons_stay_in_their_column():
    finding = Finding(
        severity=Severity.FAIL, verdict="unsupported", subject="claim", reason="word " * 40
    )
    text = render(CheckResult(check="faithfulness", passed=False, findings=[finding]), width=60)
    reason_lines = [line for line in text.splitlines() if "word" in line]
    assert len(reason_lines) > 1
    assert len({line.index("word") for line in reason_lines}) == 1


def test_no_line_has_trailing_whitespace():
    text = render(Report(results=[_faithfulness()]), width=80)
    assert all(line == line.rstrip() for line in text.splitlines())


def test_show_prints_colour_without_trailing_padding():
    out = io.StringIO()
    console = Console(file=out, width=120, force_terminal=True, color_system="standard")
    show(Report(results=[_faithfulness()]), console=console)
    printed = out.getvalue()
    assert "\x1b[" in printed
    plain = re.sub(r"\x1b\[[0-9;]*m", "", printed)
    assert all(line == line.rstrip() for line in plain.splitlines())


def test_unknown_results_are_rejected():
    with pytest.raises(TypeError, match="Cannot render dict"):
        view({})


def test_summaries_with_square_brackets_are_printed_as_written():
    report = Report(
        results=[CheckResult(check="role", passed=False, summary="Leaked [/INST] and [red]x[/red]")]
    )
    assert "Leaked [/INST] and [red]x[/red]" in render(report)


def test_a_report_with_no_scores_has_no_overall_percentage():
    report = Report(results=[CheckResult(check="injection", passed=True, summary="clean")])
    assert "overall — · 1 check" in render(report)


def test_file_and_line_locations_lead_the_finding():
    finding = Finding(
        severity=Severity.FAIL,
        verdict="payload",
        subject="ignore previous instructions",
        metadata={"file": "billing/cart.py", "line": 22, "affected_outputs": [1, 2]},
    )
    text = render(CheckResult(check="injection", passed=False, findings=[finding]))
    assert "billing/cart.py:22  affects #1, #2  ignore previous instructions" in text


def test_terminal_escapes_in_untrusted_text_are_neutralised():
    hostile = Finding(
        severity=Severity.FAIL,
        verdict="payload",
        subject="\x1b[2J\x1b]52;c;cHduZWQ=\x07wiped",
        reason="line\rover" + RLO + "flip",
        evidence="\x1b[8mhidden",
    )
    out = io.StringIO()
    console = Console(file=out, width=200, force_terminal=True, color_system="standard")
    show(
        CheckResult(check="injection", passed=False, summary="\x1b[32mfake", findings=[hostile]),
        title="task\x1b[0m",
        console=console,
    )
    printed = out.getvalue()
    for raw in ("\x1b[2J", "\x1b]52", "\x07", "\r", RLO, "\x1b[8m", "\x1b[32m"):
        assert raw not in printed
    assert "\\x1b[2J" in printed
    assert "\\u202e" in printed
