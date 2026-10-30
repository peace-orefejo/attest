import pytest

from attest.code_review.evidence.scoping import read_label, scope_evidence
from attest.code_review.models import FileRead, ReviewOutput

DIFFS = {"a.py": "diff a", "b.py": "diff b"}
READS = [
    FileRead(arguments={"path": "c.py"}, output="c"),
    FileRead(tool="grep", arguments={"pattern": "def run"}, output="a.py:3: def run"),
]


def _output(output_type, **extra):
    return ReviewOutput(
        output_type=output_type,
        text="t",
        diffs=DIFFS,
        reads=READS,
        changed_files=["a.py", "b.py"],
        **extra,
    )


def test_issue_gets_diffs_reads_and_changed_files():
    scope = scope_evidence(_output("issue"))
    assert scope.diffs == list(DIFFS.items())
    assert scope.reads == READS
    assert scope.changed_files == ["a.py", "b.py"]
    assert scope.dropped_diffs == [] and scope.dropped_reads == []


def test_diff_summary_gets_only_its_file():
    scope = scope_evidence(_output("diff_summary"))
    assert scope.diffs == [("a.py", "diff a")]
    assert scope.reads == []
    assert scope.dropped_diffs == ["b.py"]
    assert scope.dropped_reads == READS


def test_group_summary_gets_every_diff_but_no_reads():
    scope = scope_evidence(_output("group_summary", group_name="billing"))
    assert scope.diffs == list(DIFFS.items())
    assert scope.reads == []
    assert scope.changed_files == ["a.py", "b.py"]


def test_canvas_answer_gets_what_was_read_in_order():
    scope = scope_evidence(_output("canvas_answer", question="why?"))
    assert scope.reads == READS
    assert scope.diffs == list(DIFFS.items())


@pytest.mark.parametrize("output_type", ["issue", "diff_summary", "group_summary", "canvas_answer"])
def test_changed_files_absent_when_not_given(output_type):
    output = ReviewOutput(output_type=output_type, text="t", diffs=DIFFS)
    assert scope_evidence(output).changed_files is None


def test_read_label():
    assert read_label(READS[0]) == "c.py"
    assert read_label(READS[1]) == "def run"
    assert read_label(FileRead(output="x")) == "read_file"
