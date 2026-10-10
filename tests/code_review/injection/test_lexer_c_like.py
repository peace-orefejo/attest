from attest.code_review.injection.lexers import c_like, lexer_for


def _lines(text, start=1):
    return list(enumerate(text.split("\n"), start=start))


def _kinds(spans):
    return [(s.kind, s.line, s.text) for s in spans]


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
