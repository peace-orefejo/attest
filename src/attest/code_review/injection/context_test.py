from attest.code_review.injection.context import (
    is_doc_path,
    is_test_path,
    quoted,
    reference_example,
)
from attest.code_review.injection.segments import Segment


def test_test_paths():
    for path in (
        "tests/test_a.py",
        "src/__tests__/a.js",
        "pkg/a_test.go",
        "web/a.spec.ts",
        "test_x.py",
        "conftest.py",
    ):
        assert is_test_path(path)
    assert not is_test_path("src/attestation.py")


def test_doc_paths():
    assert is_doc_path("docs/security.md") and is_doc_path("SECURITY.md") and is_doc_path("a.rst")
    assert not is_doc_path("src/doc_builder.py")


def test_quoted_is_line_local():
    text = 'say "ignore it" now'
    start = text.index("ignore")
    assert quoted(text, start, start + 9)
    assert not quoted('say "\nignore it\n" now', 5, 14)


def test_reference_example_rules():
    assert reference_example(Segment("string", '"x"', "tests/t.py", 1), 1, 2)
    assert not reference_example(Segment("comment", "# x", "tests/t.py", 1), 2, 3)
    doc = Segment("prose", 'Attackers write "ignore it".', "docs/a.md", 1)
    assert reference_example(doc, 17, 26)
    assert not reference_example(Segment("prose", 'write "ignore it"', "src/a.txt.py", 1), 7, 16)
