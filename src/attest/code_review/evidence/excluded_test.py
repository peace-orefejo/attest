"""Excluded files in code review evidence: diffs, reads, grep lines and the changed-file list."""

import pytest

from attest import Exclusions
from attest.code_review import FileRead, PullRequest, ReviewOutput, to_run_with_omissions
from attest.code_review.evidence import render_diffs
from attest.code_review.evidence.excluded import (
    HiddenRead,
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


def test_a_grep_naming_an_excluded_file_is_withheld_whole():
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
        f"secrets/prod.env: {NOTE}",
        f"poetry.lock: {NOTE}",
        f"[grep output withheld: it names files {NOTE}]",
    ]
    assert hidden.excluded == ["secrets/prod.env", "poetry.lock"]
    assert hide_read(hidden.read, EXCLUDE).read.output == hidden.read.output


def test_a_grep_naming_no_excluded_file_is_kept():
    read = FileRead(tool="grep", arguments={"pattern": "y"}, output="app/main.py:2:y = 1")
    assert hide_read(read, EXCLUDE) == HiddenRead(read=read)


def test_the_search_text_is_not_treated_as_a_path():
    read = FileRead(tool="grep", arguments={"pattern": "secrets"}, output="app/a.py:1:secrets")
    assert hide_read(read, EXCLUDE).excluded == []


ANCHORED = Exclusions(patterns=("/secrets/", "fixtures/**"))


@pytest.mark.parametrize(
    ("arguments", "named"),
    [
        ({"path": "/home/u/repo/fixtures/users.json"}, "/home/u/repo/fixtures/users.json"),
        ({"path": "src/../secrets/k.env"}, "src/../secrets/k.env"),
        ({"path": "secrets\\k.env"}, "secrets\\k.env"),
        ({"path": "a/..//./secrets/k.env"}, "a/..//./secrets/k.env"),
        ({"path": "../secrets/k.env"}, "../secrets/k.env"),
        ({"path": "C:\\repo\\secrets\\k.env"}, "C:\\repo\\secrets\\k.env"),
        ({"file_path": "secrets/k.env"}, "secrets/k.env"),
        ({"paths": ["app/ok.py", "secrets/k.env"]}, "secrets/k.env"),
        ({"target": {"nested": "x"}, "filename": "/repo/secrets/k.env"}, "/repo/secrets/k.env"),
    ],
)
def test_every_path_form_of_a_read_argument_is_caught(arguments, named):
    read = FileRead(arguments=arguments, output=f"TOKEN={SECRET}")
    hidden = hide_read(read, ANCHORED)
    assert SECRET not in hidden.read.output
    assert hidden.excluded == [named]


@pytest.mark.parametrize(
    "output",
    [
        f"secrets/k.env\n1:TOKEN={SECRET}\n2-other",
        f"/home/u/repo/secrets/k.env:1:TOKEN={SECRET}",
        f"/home/u/repo/secrets/k.env\n1:TOKEN={SECRET}",
        f"secrets/k.env\x001:TOKEN={SECRET}",
        f"./src/../secrets/k.env-2-TOKEN={SECRET}",
        f"app/a.py:1:x\r\nsecrets/k.env:1:TOKEN={SECRET}",
    ],
)
def test_every_grep_output_form_naming_an_excluded_file_is_withheld(output):
    read = FileRead(tool="grep", arguments={"pattern": "TOKEN"}, output=output)
    hidden = hide_read(read, ANCHORED)
    assert SECRET not in hidden.read.output
    assert hidden.excluded
    assert hidden.read.output.endswith("[grep output withheld: it names files " + NOTE + "]")


@pytest.mark.parametrize(
    ("key", "text"),
    [
        ("b/secrets/k.env", _diff("secrets/k.env", f"TOKEN={SECRET}")),
        ("./secrets/k.env", _diff("secrets/k.env", f"TOKEN={SECRET}")),
        (
            "app/x.py",
            _diff("app/x.py", "z = 2")
            + "diff --git a/secrets/k.env b/secrets/k.env\n"
            + _diff("secrets/k.env", f"TOKEN={SECRET}"),
        ),
        (
            "app/x.py",
            _diff("app/x.py", "z = 2") + _diff("secrets/k.env", f"TOKEN={SECRET}"),
        ),
        (
            "app/k.env",
            "diff --git a/secrets/k.env b/app/k.env\nrename from secrets/k.env\n"
            "rename to app/k.env\n" + _diff("app/k.env", f"TOKEN={SECRET}"),
        ),
    ],
)
def test_a_diff_naming_an_excluded_file_in_its_key_or_headers_is_hidden(key, text):
    exclusions = Exclusions(patterns=("/secrets/",))
    pr = PullRequest(diffs={"app/main.py": DIFFS["app/main.py"], key: text})
    hidden = hide_pull_request(pr, exclusions)
    assert SECRET not in hidden.pr.model_dump_json()
    assert hidden.excluded == [key]
    assert list(without_excluded_diffs(pr, exclusions).diffs) == ["app/main.py"]
    assert SECRET not in render_diffs(list(pr.diffs.items()), exclusions=exclusions)[1].text


def test_content_lines_that_look_like_headers_do_not_hide_a_diff():
    text = _diff("app/q.sql", "x") + "--- see secrets/k.env\n+++ secrets/k.env\n context\n"
    pr = PullRequest(diffs={"app/q.sql": text})
    assert hide_pull_request(pr, Exclusions(patterns=("secrets/",))).excluded == []


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
