from attest.code_review.injection.lexers import lexer_for
from attest.code_review.injection.lexers import c_like, prose, python


def _lines(text, start=1):
    return list(enumerate(text.split("\n"), start=start))


def _kinds(spans):
    return [(s.kind, s.line, s.text) for s in spans]


def test_python_splits_comment_docstring_string_and_code():
    spans = python.lex(_lines(
        'def f():\n    """Doc line."""\n    x = "value"  # note\n    return x', start=5
    ))
    assert ("docstring", 6, '"""Doc line."""') in _kinds(spans)
    assert ("string", 7, '"value"') in _kinds(spans)
    assert ("comment", 7, "# note") in _kinds(spans)
    assert ("code", 8, "return x") in _kinds(spans)


def test_python_multiline_docstring_keeps_start_line():
    spans = python.lex(_lines('    """first\n    second\n    """', start=3))
    [doc] = [s for s in spans if s.kind == "docstring"]
    assert doc.line == 3 and doc.text.count("\n") == 2


def test_python_fstring_becomes_one_string():
    spans = python.lex(_lines('msg = f"hello {name} AI reviewer"'))
    [string] = [s for s in spans if s.kind == "string"]
    assert "AI reviewer" in string.text and string.text.startswith('f"')


def test_python_falls_back_on_partial_code():
    spans = python.lex(_lines("foo(a,\n    b)  # reviewer note\nbar("))
    assert ("comment", 2, "# reviewer note") in _kinds(spans)


def test_python_falls_back_on_bad_indentation():
    spans = python.lex(_lines("  x = 1\n y = 2  # hi"))
    assert ("comment", 2, "# hi") in _kinds(spans)


def test_c_like_comments_and_strings():
    lex = lexer_for("src/a.ts")
    spans = lex(_lines('const s = "q"; // tail\n/* block\n more */ let t = `x\ny`;'))
    kinds = _kinds(spans)
    assert ("string", 1, '"q"') in kinds
    assert ("comment", 1, "// tail") in kinds
    assert ("comment", 2, "/* block\n more */") in kinds
    assert ("string", 3, "`x\ny`") in kinds


def test_c_like_escaped_quote_and_single_line_strings():
    spans = c_like.lex_with(c_like.C_STYLE, _lines('s = "a \\" b"; c = \'x\nnext'))
    assert ("string", 1, '"a \\" b"') in _kinds(spans)
    assert ("code", 2, "next") in _kinds(spans)


def test_hash_comments_need_leading_space():
    spans = lexer_for("run.sh")(_lines('echo "$#" # count\nx=${#arr}'))
    comments = [s.text for s in spans if s.kind == "comment"]
    assert comments == ["# count"]


def test_yaml_bare_values_are_strings():
    spans = lexer_for("ci.yml")(_lines("name: deploy  # c\nkey: 'v'"))
    assert ("string", 1, "name: deploy") in _kinds(spans)
    assert ("comment", 1, "# c") in _kinds(spans)


def test_rust_single_quote_is_not_a_string():
    spans = lexer_for("lib.rs")(_lines("fn f<'a>(x: &'a str) {} // done"))
    assert [s.kind for s in spans if s.kind != "code"] == ["comment"]


def test_prose_is_one_segment():
    assert _kinds(prose.lex(_lines("one\ntwo", start=4))) == [("prose", 4, "one\ntwo")]
    assert prose.lex([]) == []


def test_lexer_for_maps_extensions():
    assert lexer_for("a/b.py") is python.lex
    assert lexer_for("README.md") is prose.lex
    assert lexer_for("notes.TXT") is prose.lex
    assert lexer_for("Dockerfile") is prose.lex
    for path in ("a.js", "a.java", "a.go", "a.c", "a.cpp", "a.cs", "a.rs", "a.kt", "a.swift",
                 "a.php", "a.rb", "a.yaml"):
        assert lexer_for(path) not in (python.lex, prose.lex)
