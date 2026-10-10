"""Hidden-Unicode detection: bidi controls, invisible characters, mixed-script words."""

import pytest

from attest.checks.injection import DEFAULT_DETECTORS, UnicodeDetector, check_injection
from attest.checks.injection.detectors.hidden_unicode import suspicious_unicode
from attest.content import TextSegment

from ._helpers import _traj

RLO = "‮"
ZWSP = "​"
ZWJ = "‍"
ZWNJ = "‌"
BOM = "﻿"


def _segment(text, **extra):
    return TextSegment(text=text, location="tool_output", source_kind="tool_output",
                       subject="fetch", step=0, **extra)


def _scan(text, **extra):
    return UnicodeDetector().scan(_segment(text, **extra))


def test_bidi_control_is_high_confidence_with_offsets():
    text = f"access = 'user{RLO} // admin'"
    [detection] = _scan(text)
    assert detection.detector == "unicode"
    assert detection.category == "hidden_unicode"
    assert detection.verdict == "suspicious"
    assert detection.confidence == 1.0
    assert detection.metadata["pattern"] == "bidi_control"
    assert detection.metadata["char_start"] == text.index(RLO)
    assert detection.metadata["char_end"] == text.index(RLO) + 1
    assert detection.metadata["codepoints"] == ["U+202E"]
    assert RLO not in detection.matched_text
    assert "<U+202E>" in detection.matched_text


def test_invisible_characters_are_grouped_and_lower_confidence():
    text = f"plain{ZWSP}text with{ZWSP}hidden{ZWSP}marks"
    [detection] = _scan(text)
    assert detection.metadata["pattern"] == "invisible"
    assert detection.verdict == "possible_injection"
    assert detection.confidence == pytest.approx(0.6)
    assert detection.metadata["occurrences"] == 3
    offsets = [i for i, ch in enumerate(text) if ch == ZWSP]
    assert detection.metadata["spans"] == [[i, i + 1] for i in offsets]
    assert detection.metadata["char_start"] == offsets[0]


def test_mixed_script_word_is_flagged_with_word_offsets():
    text = "Log in at pаypal.example to continue."
    [detection] = _scan(text)
    start = text.index("pаypal")
    assert detection.metadata["pattern"] == "mixed_script"
    assert detection.verdict == "possible_injection"
    assert detection.metadata["char_start"] == start
    assert detection.metadata["char_end"] == start + len("pаypal")
    assert detection.metadata["codepoints"] == []


def test_each_kind_gets_its_own_detection():
    text = f"pаypal{ZWSP} and {RLO}x"
    kinds = [d.metadata["pattern"] for d in _scan(text)]
    assert kinds == ["mixed_script", "invisible", "bidi_control"]


@pytest.mark.parametrize("text", [
    "The page is about cats.",
    "Café naïve résumé über",
    "Привет мир and hello world",
    f"{BOM}A file that starts with a byte order mark.",
    f"Family emoji \U0001F468{ZWJ}\U0001F469{ZWJ}\U0001F467 in a caption.",
    f"Persian می{ZWNJ}خواهم uses a non-joiner.",
    f"Devanagari क्{ZWJ}ष conjunct.",
])
def test_harmless_look_alikes_stay_clean(text):
    assert _scan(text) == []


def test_bom_after_the_start_is_flagged():
    text = f"first part{BOM}second part"
    [detection] = _scan(text)
    assert detection.metadata["pattern"] == "invisible"
    assert detection.metadata["char_start"] == text.index(BOM)


def test_joiner_between_latin_letters_is_flagged():
    [detection] = _scan(f"ad{ZWJ}min")
    assert detection.metadata["codepoints"] == ["U+200D"]


def test_leading_bom_is_flagged_when_not_at_text_start():
    grouped = suspicious_unicode(f"{BOM}continued", bom_allowed=False)
    assert list(grouped) == ["invisible"]


def test_extraction_confidence_scales_and_metadata_is_kept():
    [detection] = _scan(f"x{RLO}y", extraction_confidence=0.5, metadata={"page": 3})
    assert detection.confidence == pytest.approx(0.5)
    assert detection.verdict == "possible_injection"
    assert detection.metadata["page"] == 3
    assert detection.location == "tool_output" and detection.step == 0


def test_spans_are_capped():
    text = ZWSP.join("abcdefgh")
    [detection] = UnicodeDetector(max_spans=3).scan(_segment(text))
    assert detection.metadata["occurrences"] == 7
    assert len(detection.metadata["spans"]) == 3


@pytest.mark.parametrize("kwargs", [
    {"bidi_confidence": 1.5}, {"low_signal_confidence": -0.1},
    {"possible_threshold": 2}, {"max_spans": 0},
])
def test_invalid_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        UnicodeDetector(**kwargs)


def test_unicode_detector_is_a_default():
    assert any(isinstance(d, UnicodeDetector) for d in DEFAULT_DETECTORS)


def test_check_injection_reports_bidi_end_to_end():
    result = check_injection(_traj("normal page", f"if is_admin:{RLO} # check later"))
    [finding] = result.findings
    assert finding.step == 1
    assert finding.verdict == "suspicious"
    assert finding.metadata["detector"] == "unicode"
    assert finding.metadata["category"] == "hidden_unicode"
    assert finding.metadata["pattern"] == "bidi_control"
    assert result.passed is True


def test_check_injection_with_only_unicode_detector():
    result = check_injection(_traj(f"price{ZWSP}list"), detectors=[UnicodeDetector()])
    [finding] = result.findings
    assert finding.verdict == "possible_injection"


def test_check_injection_keeps_harmless_unicode_clean():
    text = f"{BOM}Café menu \U0001F468{ZWJ}\U0001F469 Привет"
    assert check_injection(_traj(text)).findings == []
