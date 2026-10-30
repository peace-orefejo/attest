"""Report scoring: a report with no scored check has no overall score."""

from attest.results import CheckResult, Report


def test_a_report_with_no_scored_check_has_no_overall_score():
    assert Report(results=[CheckResult(check="injection", passed=True)]).overall_score is None
    assert Report(results=[]).overall_score is None


def test_overall_score_averages_only_scored_checks():
    report = Report(
        results=[
            CheckResult(check="faithfulness", passed=True, score=None),
            CheckResult(check="tool_use", passed=True, score=0.5),
        ]
    )
    assert report.overall_score == 0.5
    assert '"overall_score":0.5' in report.model_dump_json()
