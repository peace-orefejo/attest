"""load_guidelines resolves files, text and lists, and falls back to the general standard."""

import pytest

from attest.code_review.guidelines import ReviewGuidelines, general_guidelines, load_guidelines


def test_no_guidelines_means_the_built_in_general_standard():
    guidelines = load_guidelines(None)
    assert guidelines.builtin
    assert guidelines.name == "general standard"
    assert len(guidelines.rules) >= 5
    assert any("style" in r.text.lower() for r in guidelines.rules)
    assert load_guidelines([]) == general_guidelines()


def test_a_markdown_path_is_read(tmp_path):
    path = tmp_path / "REVIEW.md"
    path.write_text("- No raw SQL.\n")
    for value in (path, str(path), [path]):
        guidelines = load_guidelines(value)
        assert guidelines.name == "REVIEW.md"
        assert not guidelines.builtin
        assert guidelines.rules[0].text == "No raw SQL."


def test_markdown_text_is_parsed_directly():
    assert load_guidelines("- Flag real bugs.\n- Be kind.\n").rules[1].text == "Be kind."


def test_several_files_merge_with_fresh_ids_and_their_sources(tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    a.write_text("- Rule A.\n")
    b.write_text("- Rule B1.\n- Rule B2.\n")
    guidelines = load_guidelines([a, b])
    assert guidelines.name == "a.md, b.md"
    assert [(r.id, r.source) for r in guidelines.rules] == [
        ("G1", "a.md"),
        ("G2", "b.md"),
        ("G3", "b.md"),
    ]


def test_a_missing_file_is_a_clear_error(tmp_path):
    with pytest.raises(ValueError, match="Could not read guidelines file"):
        load_guidelines(str(tmp_path / "missing.md"))


def test_loaded_guidelines_pass_through():
    given = ReviewGuidelines(name="x", rules=[])
    assert load_guidelines(given) is given


def test_one_line_rules_that_mention_a_file_are_text():
    assert (
        load_guidelines("- Never commit secrets to config.txt").rules[0].text
        == "Never commit secrets to config.txt"
    )


def test_an_existing_file_without_a_markdown_suffix_is_read(tmp_path):
    path = tmp_path / "REVIEW_RULES"
    path.write_text("- No raw SQL.\n")
    assert load_guidelines(str(path)).name == "REVIEW_RULES"


def test_home_is_expanded(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "rules.md").write_text("- Be kind.\n")
    assert load_guidelines("~/rules.md").rules[0].text == "Be kind."


def test_a_long_one_line_rule_is_text_not_a_path():
    rule = "- " + "Always check the return value of every call " * 20
    assert load_guidelines(rule).rules[0].text.startswith("Always check the return value")


def test_an_oversized_file_is_rejected(tmp_path):
    from attest.code_review.guidelines.parse import MAX_GUIDELINES_CHARS

    path = tmp_path / "REVIEW.md"
    path.write_text("- a\n" * (MAX_GUIDELINES_CHARS // 4 + 1))
    with pytest.raises(ValueError, match="too long"):
        load_guidelines(path)
