from attest.code_review.injection.lexers import prose


def _lines(text, start=1):
    return list(enumerate(text.split("\n"), start=start))


def _kinds(spans):
    return [(s.kind, s.line, s.text) for s in spans]


def test_prose_is_one_segment():
    assert _kinds(prose.lex(_lines("one\ntwo", start=4))) == [("prose", 4, "one\ntwo")]
    assert prose.lex([]) == []
