"""Markdown review guides become numbered rules under their nearest heading."""

import pytest

from attest.code_review.guidelines import parse_guidelines

GUIDE = """# Team review rules

Intro paragraph that is not a rule.

## Security
- Flag any SQL built with string formatting.
- Never approve code that logs **access tokens**.
  This includes `debug` logs.

## Style
1. Do not flag formatting; the linter handles it.
2. [x] Issues must say which function they are about.
   - Sub-point: include the file name too.

```python
query = f"SELECT * FROM users WHERE id = {user_id}"
```
<!-- - hidden rule -->
"""


def test_list_items_become_numbered_rules_with_sections():
    guidelines = parse_guidelines(GUIDE, "REVIEW.md")
    assert [(r.id, r.section) for r in guidelines.rules] == [
        ("G1", "Security"),
        ("G2", "Security"),
        ("G3", "Style"),
        ("G4", "Style"),
    ]
    assert guidelines.rules[0].text == "Flag any SQL built with string formatting."
    assert guidelines.rules[0].source == "REVIEW.md"
    assert guidelines.name == "REVIEW.md"


def test_continuations_sub_items_and_code_join_their_rule():
    rules = parse_guidelines(GUIDE).rules
    assert rules[1].text == "Never approve code that logs access tokens. This includes debug logs."
    assert rules[3].text.startswith(
        "Issues must say which function they are about. Sub-point: include"
    )
    assert 'query = f"SELECT' in rules[3].text


def test_paragraphs_and_comments_are_not_rules_when_lists_exist():
    texts = [r.text for r in parse_guidelines(GUIDE).rules]
    assert not any("Intro paragraph" in t or "hidden rule" in t for t in texts)


def test_a_guide_without_lists_uses_paragraphs():
    rules = parse_guidelines("# Rules\n\nBe kind.\n\nFlag real bugs\nonly.\n").rules
    assert [r.text for r in rules] == ["Be kind.", "Flag real bugs only."]


def test_an_empty_guide_is_rejected():
    with pytest.raises(ValueError, match=r"No review rules found in empty\.md"):
        parse_guidelines("# Title only\n", "empty.md")


def test_render_groups_rules_under_sections():
    rendered = parse_guidelines(GUIDE).render()
    assert rendered.startswith("## Security\nG1: Flag any SQL")
    assert "## Style\nG3: Do not flag formatting" in rendered


def test_an_unindented_continuation_line_stays_with_its_rule():
    rules = parse_guidelines(
        "- Do not flag style\nunless it hides a bug.\n\nA paragraph after.\n"
    ).rules
    assert [r.text for r in rules] == ["Do not flag style unless it hides a bug."]


def test_identifiers_with_underscores_and_code_spans_survive():
    rules = parse_guidelines(
        "- Never edit `__init__.py` or **generated** files.\n- Keep snake__case names.\n"
    ).rules
    assert [r.text for r in rules] == [
        "Never edit __init__.py or generated files.",
        "Keep snake__case names.",
    ]


def test_horizontal_rules_are_not_rules():
    rules = parse_guidelines("- One.\n\n* * *\n\n- - -\n---\n- Two.\n").rules
    assert [r.text for r in rules] == ["One.", "Two."]


def test_a_fence_closes_only_with_its_own_marker():
    rules = parse_guidelines("- a\n```\nx\n~~~\n- inside\n```\n- b\n").rules
    assert [r.text for r in rules] == ["a x ~~~ - inside", "b"]


def test_an_unclosed_comment_hides_the_rest_of_the_file():
    rules = parse_guidelines("- Visible.\n<!-- start of a hidden part\n- Hidden rule.\n").rules
    assert [r.text for r in rules] == ["Visible."]


def test_many_unclosed_comments_parse_quickly():
    import time

    started = time.perf_counter()
    rules = parse_guidelines("- Rule.\n" + "<!-- x " * 20_000).rules
    assert [r.text for r in rules] == ["Rule."]
    assert time.perf_counter() - started < 1


def test_an_oversized_guide_is_rejected():
    from attest.code_review.guidelines.parse import MAX_GUIDELINES_CHARS

    with pytest.raises(ValueError, match="too long"):
        parse_guidelines("- a\n" * (MAX_GUIDELINES_CHARS // 4 + 1), "huge.md")
