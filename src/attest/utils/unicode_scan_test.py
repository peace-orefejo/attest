from attest.utils.unicode_scan import mixed_script, scan_unicode


def test_finds_bidi_controls_with_positions():
    text = "a\u202eb\u2066c\u2069"
    hits = scan_unicode(text)
    assert [(h.kind, h.start) for h in hits] == [
        ("bidi_control", 1),
        ("bidi_control", 3),
        ("bidi_control", 5),
    ]
    assert hits[0].codepoints == ["U+202E"]


def test_covers_every_bidi_control_in_range():
    for code in list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A)):
        assert scan_unicode(f"x{chr(code)}y")[0].kind == "bidi_control"


def test_finds_invisible_characters():
    for ch in ("\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"):
        hits = scan_unicode(f"ab{ch}cd")
        assert [(h.kind, h.start, h.end) for h in hits] == [("invisible", 2, 3)]


def test_flags_latin_cyrillic_identifier():
    hits = scan_unicode("def check_p\u0430ssword(x):")
    assert [(h.kind, h.text) for h in hits] == [("mixed_script", "check_p\u0430ssword")]
    assert hits[0].start == 4


def test_flags_latin_greek_identifier():
    assert mixed_script("t\u03bfken")


def test_single_script_words_are_not_mixed():
    assert not mixed_script("\u03c0\u03b1\u03c1")
    assert not mixed_script("\u043f\u0440\u0438\u0432\u0435\u0442")
    assert not mixed_script("na\u00efve_caf\u00e9")
    assert scan_unicode("\u03c0 = 3.14 and \u043f\u0440\u0438\u0432\u0435\u0442 world") == []


def test_plain_ascii_is_clean():
    assert scan_unicode("def add(a, b):\n    return a + b\n") == []


def test_hits_are_sorted_by_position():
    hits = scan_unicode("\u0430bc \u200b x\u202e")
    assert [h.start for h in hits] == sorted(h.start for h in hits)


def test_finds_tag_characters_and_invisible_operators():
    smuggled = "".join(chr(0xE0000 + ord(ch)) for ch in "hi")
    hits = scan_unicode(f"ok{smuggled}\u2062")
    assert [(h.kind, h.start) for h in hits] == [
        ("invisible", 2),
        ("invisible", 3),
        ("invisible", 4),
    ]
    assert hits[0].codepoints == ["U+E0068"]
