"""check_findings(): the one-call entry point for review bots — all offline."""

import pytest

from attest import Attest, CheckedFinding, CheckResult, Finding, Report, Severity, check_findings
from attest.findings import split_diff

CART = (
    "diff --git a/billing/cart.py b/billing/cart.py\n"
    "index 1111111..2222222 100644\n"
    "--- a/billing/cart.py\n"
    "+++ b/billing/cart.py\n"
    "@@ -18,8 +18,9 @@ def cart_total(items, user):\n"
    "-    if user is None:\n"
    '-        raise ValueError("user required")\n'
    "+    discount = user.discount\n"
    "     total = 0\n"
)
README = (
    "diff --git a/README.md b/README.md\n"
    "--- a/README.md\n"
    "+++ b/README.md\n"
    "@@ -1 +1 @@\n"
    "-old\n"
    "+new\n"
)
DELETED = (
    "diff --git a/old.py b/old.py\n"
    "deleted file mode 100644\n"
    "--- a/old.py\n"
    "+++ /dev/null\n"
    "@@ -1 +0,0 @@\n"
    "-x = 1\n"
)
BINARY = "diff --git a/logo.png b/logo.png\nBinary files a/logo.png and b/logo.png differ\n"


def test_split_diff_keys_each_file_of_a_git_diff():
    diffs = split_diff(CART + README + DELETED + BINARY)
    assert list(diffs) == ["billing/cart.py", "README.md", "old.py", "logo.png"]
    assert diffs["billing/cart.py"] == CART
    assert diffs["old.py"] == DELETED


def test_split_diff_handles_plain_unified_diffs_without_git_headers():
    plain = (
        "--- a/one.py\t2026-01-01\n+++ b/one.py\t2026-01-02\n@@ -1 +1 @@\n-a\n+b\n"
        "--- two.py\n+++ two.py\n@@ -1 +1 @@\n-c\n+d\n"
    )
    assert list(split_diff(plain)) == ["one.py", "two.py"]


def test_split_diff_keeps_a_removed_line_that_looks_like_a_header_in_its_file():
    sql = (
        "--- a/q.sql\n+++ b/q.sql\n@@ -1,2 +1,2 @@\n--- old comment\n+++ new comment\n select 1;\n"
    )
    assert split_diff(sql) == {"q.sql": sql}


def test_split_diff_ignores_preamble_and_refuses_a_hunk_with_no_file():
    assert list(split_diff("Some notes\n" + README)) == ["README.md"]
    with pytest.raises(ValueError, match="file name"):
        split_diff("@@ -1 +1 @@\n-a\n+b\n")


def _report(*verdicts):
    severity = {"supported": Severity.PASS, "unsupported": Severity.FAIL}
    return Report(
        results=[
            CheckResult(
                check="faithfulness",
                passed="unsupported" not in verdicts,
                summary=f"{verdicts.count('supported')}/{len(verdicts)} checkable claims grounded.",
                findings=[
                    Finding(
                        severity=severity[v],
                        verdict=v,
                        subject=f"claim {i}",
                        reason="the diff shows otherwise" if v == "unsupported" else "",
                    )
                    for i, v in enumerate(verdicts)
                ],
            )
        ]
    )


@pytest.fixture
def graded(monkeypatch):
    """Grade each output by its text: 'BAD' outputs make an unsupported claim."""
    runs = []

    def fake_evaluate(self, run, **kwargs):
        runs.append(run)
        return _report("unsupported" if "BAD" in run.final_answer else "supported")

    monkeypatch.setattr(Attest, "evaluate", fake_evaluate)
    return runs


def test_check_findings_keeps_supported_findings_and_drops_the_rest(graded):
    results = check_findings(
        CART + README,
        ["user.discount raises when user is None.", "BAD: the loop is off by one."],
        answers={"Does this change the API?": "No, only cart_total's body changed."},
        attest=Attest(key="sk-ant-test-key"),
    )
    assert [type(r) for r in results] == [CheckedFinding] * 3
    assert [r.keep for r in results] == [True, False, True]
    assert results[0].reason == "1/1 checkable claims grounded."
    assert results[0].reasons == []
    assert results[1].text == "BAD: the loop is off by one."
    assert results[1].reason == "unsupported: claim 0 (the diff shows otherwise)"
    assert results[2].question == "Does this change the API?"
    assert len(graded) == 3


def test_check_findings_accepts_a_path_mapping(graded):
    results = check_findings(
        {"billing/cart.py": CART}, ["fine"], attest=Attest(key="sk-ant-test-key")
    )
    assert [r.keep for r in results] == [True]


def test_check_findings_only_checks_review_rules_when_given(monkeypatch, graded):
    seen = []
    real = Attest.review

    def spy(self, pr, outputs, **kwargs):
        seen.append(kwargs["follow_guidelines"])
        return real(self, pr, outputs, **{**kwargs, "follow_guidelines": False})

    monkeypatch.setattr(Attest, "review", spy)
    judge = Attest(key="sk-ant-test-key")
    check_findings(CART, ["fine"], attest=judge)
    check_findings(CART, ["fine"], attest=judge, guidelines="- Do not flag formatting.\n")
    assert seen == [False, True]


@pytest.mark.parametrize(
    ("diff", "findings", "answers", "error"),
    [
        (CART, [], None, "at least one"),
        ("", ["x"], None, "empty"),
        ({}, ["x"], None, "empty"),
        (CART, "one finding", None, "list"),
    ],
)
def test_check_findings_rejects_bad_input_before_any_model_call(
    monkeypatch, diff, findings, answers, error
):
    def fail(*args, **kwargs):
        raise AssertionError("nothing should run")

    monkeypatch.setattr(Attest, "review", fail)
    with pytest.raises((ValueError, TypeError), match=error):
        check_findings(diff, findings, answers=answers, key="sk-ant-test-key")
