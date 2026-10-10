from attest.utils.unicode_scan import mixed_script, scan_unicode


def test_finds_bidi_controls_with_positions():
    text = "a‮b⁦c⁩"
    hits = scan_unicode(text)
    assert [(h.kind, h.start) for h in hits] == [
        ("bidi_control", 1), ("bidi_control", 3), ("bidi_control", 5)
    ]
    assert hits[0].codepoints == ["U+202E"]


def test_covers_every_bidi_control_in_range():
    for code in list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A)):
        assert scan_unicode(f"x{chr(code)}y")[0].kind == "bidi_control"


def test_finds_invisible_characters():
    for ch in ("​", "‌", "‍", "⁠", "﻿"):
        hits = scan_unicode(f"ab{ch}cd")
        assert [(h.kind, h.start, h.end) for h in hits] == [("invisible", 2, 3)]


def test_flags_latin_cyrillic_identifier():
    hits = scan_unicode("def check_pаssword(x):")
    assert [(h.kind, h.text) for h in hits] == [("mixed_script", "check_pаssword")]
    assert hits[0].start == 4


def test_flags_latin_greek_identifier():
    assert mixed_script("tοken")


def test_single_script_words_are_not_mixed():
    assert not mixed_script("παρ")
    assert not mixed_script("привет")
    assert not mixed_script("naïve_café")
    assert scan_unicode("π = 3.14 and привет world") == []


def test_plain_ascii_is_clean():
    assert scan_unicode("def add(a, b):\n    return a + b\n") == []


def test_hits_are_sorted_by_position():
    hits = scan_unicode("аbc ​ x‮")
    assert [h.start for h in hits] == sorted(h.start for h in hits)
