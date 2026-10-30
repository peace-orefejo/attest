"""terminal_safe(): control and bidi characters become visible escapes."""

from attest.display.sanitize import terminal_safe

RLO = chr(0x202E)
LRI = chr(0x2066)


def test_plain_text_tabs_and_newlines_pass_through():
    assert terminal_safe("a\tb\nc — ✓") == "a\tb\nc — ✓"


def test_escape_sequences_and_carriage_returns_are_escaped():
    assert terminal_safe("\x1b[31mred\r") == "\\x1b[31mred\\x0d"


def test_c1_controls_and_bidi_overrides_are_escaped():
    assert terminal_safe("\x9bx" + RLO + "y" + LRI) == "\\x9bx\\u202ey\\u2066"
