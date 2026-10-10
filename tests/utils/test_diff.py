from attest.utils.diff import cut_hunks, parse_unified_diff

DIFF = """--- a/billing/cart.py
+++ b/billing/cart.py
@@ -21,6 +21,6 @@ def cart_total(items):
     total = 0
-    for i in range(len(items) - 1):
+    for i in range(len(items)):
         total += items[i].price
     return total
@@ -40,2 +40,3 @@
 x = 1
+y = 2
 z = 3
"""


def test_parses_files_hunks_and_line_numbers():
    [file_diff] = parse_unified_diff(DIFF)
    assert file_diff.path == "billing/cart.py"
    assert len(file_diff.hunks) == 2
    assert file_diff.added_lines() == [(22, "    for i in range(len(items)):"), (41, "y = 2")]
    assert file_diff.changed_line_count() == 3


def test_headerless_diff_uses_given_path():
    [file_diff] = parse_unified_diff("@@ -1,1 +1,1 @@\n-a\n+b\n", path="x.py")
    assert file_diff.path == "x.py"
    assert file_diff.added_lines() == [(1, "b")]


def test_multiple_files():
    two = DIFF + "--- a/r.md\n+++ b/r.md\n@@ -1,0 +1,1 @@\n+hello\n"
    assert [f.path for f in parse_unified_diff(two)] == ["billing/cart.py", "r.md"]


def test_cut_hunks_keeps_first_hunk_and_counts_omitted():
    [file_diff] = parse_unified_diff(DIFF)
    text, omitted = cut_hunks(file_diff, max_chars=10)
    assert text.startswith("@@ -21,6 +21,6 @@")
    assert omitted == 1
    full, none = cut_hunks(file_diff, max_chars=10_000)
    assert none == 0 and "+y = 2" in full
