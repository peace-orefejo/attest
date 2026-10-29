"""render(): every result type becomes a structured, aligned, plain-text view."""

import io
import re

import pytest
from rich.console import Console

from attest import CheckResult, Finding, Report, Severity, render, show
from attest.code_review import GateDecision, OutputDecision, ReviewResult
from attest.code_review.guidelines import general_guidelines, parse_guidelines
from attest.display.theme import Truncated


def _faithfulness() -> CheckResult:
    return CheckResult(check="faithfulness", passed=False, score=0.5, summary="1/2 checkable claims grounded.",
                       findings=[
                           Finding(severity=Severity.FAIL, verdict="unsupported", subject="Paris is larger",
                                   reason="Berlin is larger.", evidence="Berlin population: 3,677,000"),
                           Finding(severity=Severity.PASS, verdict="supported", subject="Berlin has 3.7M",
                                   reason="hidden for passes"),
                       ])


def _injection(*findings: Finding) -> CheckResult:
    return CheckResult(check="code_injection", passed=not findings, summary="scan summary",
                       findings=list(findings), metadata={"verdict": "compromised" if findings else "clean"})


def test_report_has_a_header_a_summary_table_and_details():
    report = Report(results=[_faithfulness(), CheckResult(check="tool_use", passed=True, score=1.0, summary="ok")])
    text = render(report, title="Which is larger?")
    lines = text.splitlines()
    assert lines[0].startswith("FAIL  Which is larger?")
    assert "overall 75% · 2 checks" in lines[1]
    assert any(line.split() == ["faithfulness", "50%", "FAIL", "1/2", "checkable", "claims", "grounded."]
               for line in lines)
    assert any(line.split()[:3] == ["tool_use", "100%", "PASS"] for line in lines)
    assert "✗  unsupported  Paris is larger" in text
    assert "evidence  Berlin population: 3,677,000" in text
    assert "✓  supported    Berlin has 3.7M" in text
    assert "hidden for passes" not in text


def test_check_result_without_a_score_says_nothing_about_score():
    text = render(CheckResult(check="injection", passed=True, summary="Nothing found."), title="task")
    assert "score" not in text
    assert "injection · Nothing found." in text


def test_wrapped_reasons_stay_in_their_column():
    finding = Finding(severity=Severity.FAIL, verdict="unsupported", subject="claim", reason="word " * 40)
    text = render(CheckResult(check="faithfulness", passed=False, findings=[finding]), width=60)
    reason_lines = [line for line in text.splitlines() if "word" in line]
    assert len(reason_lines) > 1
    assert len({line.index("word") for line in reason_lines}) == 1


def test_no_line_has_trailing_whitespace():
    text = render(Report(results=[_faithfulness()]), width=80)
    assert all(line == line.rstrip() for line in text.splitlines())


def _review() -> ReviewResult:
    compromised = Finding(severity=Severity.FAIL, verdict="compromised", subject="billing/cart.py:22",
                          reason="Output 1 repeats the payload.",
                          metadata={"file": "billing/cart.py", "line": 22, "affected_outputs": [1]})
    return ReviewResult(
        injection=_injection(compromised),
        decisions=[
            OutputDecision(index=0, output_type="issue", text="real bug", keep=True, mode="lenient",
                           score=1.0, summary="1/1 grounded.", notes=[compromised]),
            OutputDecision(index=1, output_type="issue", text="the index is checked by the caller " * 10,
                           keep=False, mode="lenient", score=1.0, summary="1/1 grounded.",
                           reasons=[compromised]),
        ],
    )


def test_review_shows_counts_injection_a_row_per_output_and_why_drops_dropped():
    text = render(_review())
    lines = text.splitlines()
    assert lines[0].startswith("DROP 1  Code review")
    assert "1 kept · 1 dropped · 2 outputs" in lines[1]
    assert "injection  compromised  scan summary" in text
    assert "affects #1  billing/cart.py:22" in text
    assert any(line.split()[:5] == ["0", "issue", "lenient", "100%", "KEEP"] for line in lines)
    assert any(line.split()[:5] == ["1", "issue", "lenient", "100%", "DROP"] for line in lines)
    assert any(line.endswith("…") for line in lines)
    assert "#1 issue  DROP  1/1 grounded." in text
    assert "#0 issue" not in text


def test_review_names_the_guidelines_and_who_wrote_it():
    result = _review().model_copy(update={
        "guidelines": parse_guidelines("- Rule one.\n- Rule two.\n", "REVIEW.md"), "written": True})
    text = render(result)
    assert "· written by attest" in text.splitlines()[1]
    assert "guidelines  REVIEW.md    2 rules · checked" in text
    assert text.index("guidelines") < text.index("injection")
    general = _review().model_copy(update={"guidelines": general_guidelines()})
    assert "guidelines" not in render(general)
    written = render(general.model_copy(update={"written": True}))
    assert "general standard (built-in)" in written and "guided attest's review" in written


def test_show_prints_colour_without_trailing_padding():
    out = io.StringIO()
    show(_review(), console=Console(file=out, width=120, force_terminal=True, color_system="standard"))
    printed = out.getvalue()
    assert "\x1b[" in printed
    plain = re.sub(r"\x1b\[[0-9;]*m", "", printed)
    assert all(line == line.rstrip() for line in plain.splitlines())


def test_all_kept_review_says_keep():
    result = ReviewResult(injection=_injection(), decisions=[
        OutputDecision(index=0, output_type="diff_summary", keep=True, mode="strict", score=1.0)])
    assert render(result).startswith("KEEP  Code review")


def test_gate_decision_lists_reasons_and_notes_apart():
    decision = GateDecision(
        keep=False, mode="strict",
        reasons=[Finding(severity=Severity.WARN, verdict="unverifiable", subject="claim")],
        notes=[Finding(severity=Severity.WARN, verdict="suspicious", subject="a.py:3")],
    )
    text = render(decision)
    assert text.startswith("DROP  Gate decision")
    assert text.index("unverifiable") < text.index("notes") < text.index("suspicious")


def test_unknown_results_are_rejected():
    with pytest.raises(TypeError, match="Cannot render dict"):
        render({})


def test_truncated_cells_end_in_an_ellipsis():
    out = io.StringIO()
    Console(file=out, width=12, color_system=None).print(Truncated("a long line of text"))
    assert out.getvalue().strip() == "a long line…"


def test_a_kept_output_shows_its_own_notes_but_not_injection_notes():
    missed = Finding(severity=Severity.WARN, verdict="misses_guideline", subject="G3: Point to where an issue is")
    result = _review()
    result.decisions[0].notes.append(missed)
    text = render(result)
    section = text[text.index("#0 issue  KEEP"):text.index("#1 issue")]
    assert "notes" in section
    assert "misses_guideline  G3: Point to where an issue is" in section
    assert "compromised" not in section


def test_summaries_with_square_brackets_are_printed_as_written():
    report = Report(results=[CheckResult(check="role", passed=False, summary="Leaked [/INST] and [red]x[/red]")])
    assert "Leaked [/INST] and [red]x[/red]" in render(report)


def test_a_report_with_no_scores_has_no_overall_percentage():
    report = Report(results=[CheckResult(check="injection", passed=True, summary="clean")])
    assert "overall — · 1 check" in render(report)


def test_review_warnings_are_shown():
    result = _review().model_copy(update={"warnings": ["This pull request changes REVIEW.md."]})
    lines = render(result).splitlines()
    warning = next(i for i, line in enumerate(lines) if line.startswith("warning"))
    assert lines[warning].split() == ["warning", "!", "This", "pull", "request", "changes", "REVIEW.md."]
    assert lines[warning + 1].startswith("injection")
