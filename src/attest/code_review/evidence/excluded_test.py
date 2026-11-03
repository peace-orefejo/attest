"""Excluded files in code review evidence: diffs, reads, grep lines and the changed-file list."""

from attest import Exclusions
from attest.code_review import FileRead, PullRequest, ReviewOutput, to_run_with_omissions
from attest.code_review.evidence import render_diffs
from attest.code_review.evidence.excluded import (
    changed_files_listing,
    hide_output,
    hide_pull_request,
    hide_read,
    without_excluded_diffs,
)

SECRET = "MARKER-review-91ab"
EXCLUDE = Exclusions(patterns=("secrets/", "*.lock"))
NOTE = "excluded by the user's exclusion rules"


def _diff(path: str, line: str) -> str:
    return f"--- a/{path}\n+++ b/{path}\n@@ -1,1 +1,2 @@\n x = 0\n+{line}\n"


DIFFS = {
    "app/main.py": _diff("app/main.py", "y = 1"),
    "secrets/prod.env": _diff("secrets/prod.env", f"TOKEN={SECRET}"),
    "poetry.lock": _diff("poetry.lock", f'name = "{SECRET}"'),
}


def test_excluded_diffs_render_as_notes_and_use_no_budget():
    rendered = render_diffs(list(DIFFS.items()), exclusions=EXCLUDE)
    assert [item.text for item in rendered[1:]] == [
        f"secrets/prod.env: {NOTE}",
        f"poetry.lock: {NOTE}",
    ]
    assert [item.omission and item.omission.reason for item in rendered] == [
        None,
        "excluded",
        "excluded",
    ]
    assert SECRET not in "".join(item.text for item in rendered)


def test_a_negation_cannot_re_include_a_generated_file():
    rendered = render_diffs(
        [("vendor/lib.js", _diff("vendor/lib.js", "x()"))],
        exclusions=Exclusions(patterns=("!vendor/lib.js",)),
    )
    assert rendered[0].omission is not None
    assert rendered[0].omission.reason == "generated"


def test_the_changed_file_list_stays_complete_but_marks_excluded_files():
    listing = changed_files_listing(["app/main.py", "secrets/prod.env"], EXCLUDE)
    assert listing == ["app/main.py", f"secrets/prod.env ({NOTE})"]
    assert changed_files_listing(["a"], None) == ["a"]


def test_a_read_of_an_excluded_file_becomes_a_note():
    read = FileRead(arguments={"path": "secrets/prod.env"}, output=f"TOKEN={SECRET}")
    hidden = hide_read(read, EXCLUDE)
    assert hidden.read.output == f"secrets/prod.env: {NOTE}"
    assert hidden.excluded == ["secrets/prod.env"]


def test_a_grep_inside_an_excluded_directory_becomes_a_note():
    read = FileRead(tool="grep", arguments={"path": "secrets"}, output=f"a.env:1:{SECRET}")
    assert hide_read(read, EXCLUDE).read.output == f"secrets: {NOTE}"


def test_a_grep_loses_only_the_excluded_files_lines():
    output = "\n".join(
        [
            "app/main.py:2:y = 1",
            f"secrets/prod.env:1:TOKEN={SECRET}",
            f"secrets/prod.env-2-OTHER={SECRET}",
            f"poetry.lock:{SECRET}",
            "app/util.py-3-context",
        ]
    )
    read = FileRead(tool="grep", arguments={"pattern": "TOKEN"}, output=output)
    hidden = hide_read(read, EXCLUDE)
    assert SECRET not in hidden.read.output
    assert hidden.read.output.split("\n") == [
        "app/main.py:2:y = 1",
        f"secrets/prod.env: {NOTE}",
        f"poetry.lock: {NOTE}",
        "app/util.py-3-context",
    ]
    assert hidden.excluded == ["secrets/prod.env", "poetry.lock"]
    assert hide_read(hidden.read, EXCLUDE).read.output == hidden.read.output


def test_hiding_an_output_covers_diffs_reads_and_changed_files():
    output = ReviewOutput(
        output_type="issue",
        text="TOKEN is hard-coded.",
        diffs=DIFFS,
        changed_files=list(DIFFS),
        reads=[FileRead(arguments={"path": "secrets/prod.env"}, output=SECRET)],
    )
    hidden = hide_output(output, EXCLUDE)
    assert SECRET not in hidden.output.model_dump_json()
    assert hidden.excluded == ["secrets/prod.env", "poetry.lock"]
    assert hidden.output.diffs["app/main.py"] == DIFFS["app/main.py"]
    assert hide_output(output, Exclusions()).output is output


def test_hiding_the_pull_request_and_dropping_its_excluded_diffs_for_the_scan():
    pr = PullRequest(diffs=DIFFS, changed_files=[*DIFFS, "secrets/deleted.env"])
    hidden = hide_pull_request(pr, EXCLUDE)
    assert SECRET not in hidden.pr.model_dump_json()
    assert hidden.excluded == ["secrets/prod.env", "poetry.lock", "secrets/deleted.env"]
    assert list(without_excluded_diffs(pr, EXCLUDE).diffs) == ["app/main.py"]
    assert without_excluded_diffs(pr, Exclusions()) is pr


def test_the_run_for_an_output_holds_only_notes_for_excluded_files():
    output = ReviewOutput(
        output_type="canvas_answer",
        question="What changed?",
        text="y is set to 1.",
        diffs=DIFFS,
        changed_files=list(DIFFS),
        reads=[
            FileRead(arguments={"path": "secrets/prod.env"}, output=SECRET),
            FileRead(tool="grep", arguments={"pattern": "x"}, output=f"poetry.lock:{SECRET}"),
        ],
    )
    run, omissions = to_run_with_omissions(output, exclude=["secrets/", "*.lock"])
    evidence = run.evidence()
    assert SECRET not in evidence
    assert f"secrets/prod.env ({NOTE})" in evidence
    assert [(o.path, o.reason) for o in omissions] == [
        ("secrets/prod.env", "excluded"),
        ("poetry.lock", "excluded"),
        ("secrets/prod.env", "excluded"),
        ("poetry.lock", "excluded"),
    ]
