from attest.code_review.injection.lexers import python


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
