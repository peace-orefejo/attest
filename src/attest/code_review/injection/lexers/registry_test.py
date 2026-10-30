from attest.code_review.injection.lexers import lexer_for, prose, python


def test_lexer_for_maps_extensions():
    assert lexer_for("a/b.py") is python.lex
    assert lexer_for("README.md") is prose.lex
    assert lexer_for("notes.TXT") is prose.lex
    assert lexer_for("Dockerfile") is prose.lex
    for path in (
        "a.js",
        "a.java",
        "a.go",
        "a.c",
        "a.cpp",
        "a.cs",
        "a.rs",
        "a.kt",
        "a.swift",
        "a.php",
        "a.rb",
        "a.yaml",
    ):
        assert lexer_for(path) not in (python.lex, prose.lex)
