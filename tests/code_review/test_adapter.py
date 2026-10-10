from attest.code_review.adapter import task_text, to_run, to_run_with_omissions
from attest.code_review.evidence.large_files import EvidenceLimits, Omission
from attest.code_review.models import FileRead, ReviewOutput
from attest.code_review.tool_names import EVIDENCE_TOOLS
from attest.trajectory import Trajectory

CART_DIFF = """--- a/billing/cart.py
+++ b/billing/cart.py
@@ -21,4 +21,4 @@ def cart_total(items):
     total = 0
-    for i in range(len(items) - 1):
+    for i in range(len(items)):
         total += items[i].price
"""
LOCK_DIFF = "@@ -1,2 +1,2 @@\n-github.com/x/y v1.0.0 h1:abc=\n+github.com/x/y v1.2.0 h1:def=\n"
CHANGED = ["billing/cart.py", "go.sum", "README.md"]


def _issue(**extra):
    return ReviewOutput(
        output_type="issue",
        text="The loop now includes the last item.",
        diffs={"billing/cart.py": CART_DIFF},
        changed_files=CHANGED,
        reads=[
            FileRead(arguments={"path": "billing/models.py"}, output="class Item: ..."),
            FileRead(tool="grep", arguments={"pattern": "cart_total"}, output="api.py:9"),
        ],
        **extra,
    )


def test_run_validates_and_evidence_holds_scoped_diff():
    run = to_run(_issue())
    assert Trajectory.model_validate(run.model_dump()) == run
    evidence = run.evidence()
    assert "+    for i in range(len(items)):" in evidence
    assert "billing/cart.py\ngo.sum\nREADME.md" in evidence
    assert "class Item: ..." in evidence
    assert run.artifacts == []


def test_step_order_and_tools():
    run = to_run(_issue())
    calls = [tc for _, tc in run.tool_calls()]
    assert [c.name for c in calls] == ["list_changed_files", "read_diff", "read_file", "grep"]
    assert calls[1].arguments == {"path": "billing/cart.py"}
    assert calls[3].arguments == {"pattern": "cart_total"}
    assert run.allowed_tools == list(EVIDENCE_TOOLS)
    assert run.final_answer == "The loop now includes the last item."


def test_no_changed_files_step_when_not_given():
    run = to_run(ReviewOutput(output_type="diff_summary", text="s", diffs={"a.py": CART_DIFF}))
    assert [tc.name for _, tc in run.tool_calls()] == ["read_diff"]


def test_task_text_per_output_type():
    assert task_text(_issue()) == "Review the diff and report bugs."
    assert task_text(ReviewOutput(output_type="diff_summary", text="")) == "Summarise this diff."
    group = ReviewOutput(output_type="group_summary", text="", group_name="Billing fixes")
    assert task_text(group) == 'Summarise the group "Billing fixes".'
    canvas = ReviewOutput(output_type="canvas_answer", text="", question="Does this add a migration?")
    assert task_text(canvas) == "Does this add a migration?"


def test_group_summary_summarizes_lockfile_and_reports_omissions():
    output = ReviewOutput(
        output_type="group_summary",
        text="Fixes the cart loop and bumps x/y.",
        diffs={"billing/cart.py": CART_DIFF, "go.sum": LOCK_DIFF},
        changed_files=CHANGED,
        reads=[FileRead(arguments={"path": "notes.md"}, output="n")],
        group_name="Billing",
    )
    run, omissions = to_run_with_omissions(output)
    evidence = run.evidence()
    assert "github.com/x/y  v1.0.0 -> v1.2.0" in evidence
    assert "h1:abc=" not in evidence
    assert "notes.md" not in evidence
    assert omissions == [
        Omission("go.sum", "summarized", 2),
        Omission("notes.md", "out_of_scope"),
    ]


def test_diff_summary_drops_other_files():
    output = ReviewOutput(
        output_type="diff_summary",
        text="s",
        diffs={"billing/cart.py": CART_DIFF, "go.sum": LOCK_DIFF},
    )
    run, omissions = to_run_with_omissions(output)
    assert "go.sum" not in run.evidence()
    assert omissions == [Omission("go.sum", "out_of_scope")]


def test_changed_file_list_is_never_cut():
    many = [f"src/module_{i}.py" for i in range(5_000)]
    output = ReviewOutput(output_type="issue", text="t", diffs={"a.py": CART_DIFF},
                          changed_files=many)
    run = to_run(output, limits=EvidenceLimits(max_file_chars=100, max_run_chars=200))
    listing = run.tool_calls()[0][1]
    assert listing.output.splitlines() == many


def test_limits_apply_to_diffs():
    output = _issue()
    run, omissions = to_run_with_omissions(output, limits=EvidenceLimits(max_run_chars=10))
    assert omissions[0].reason == "budget"
    assert "range(len(items))" not in run.evidence()


def test_canvas_answer_keeps_reads_in_order():
    reads = [FileRead(arguments={"path": f"f{i}.py"}, output=f"body {i}") for i in range(3)]
    output = ReviewOutput(output_type="canvas_answer", text="a", question="q", reads=reads)
    run = to_run(output)
    assert [tc.arguments["path"] for _, tc in run.tool_calls()] == ["f0.py", "f1.py", "f2.py"]
