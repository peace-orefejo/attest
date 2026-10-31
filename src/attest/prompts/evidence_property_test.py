"""Property tests: content and attribute values can never open, close or escape a block."""

import html
import json
import re

import pytest

pytest.importorskip("hypothesis")

from hypothesis import given
from hypothesis import strategies as st

from attest.prompts.evidence import artifact_block, escape_block_tags, evidence_block

TAG_FRAGMENTS = [
    "<tool_output",
    "</tool_output>",
    "< / TOOL_OUTPUT >",
    "<\t/tool_output",
    "<artifact",
    "</artifact>",
    "</ ARTIFACT>",
    "<\nartifact",
    '"',
    "'",
    "&",
    "&lt;",
    "&quot;",
    "<",
    ">",
    "/",
    "\n",
]

hostile_text = st.lists(st.one_of(st.text(), st.sampled_from(TAG_FRAGMENTS)), max_size=6).map(
    "".join
)
json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    hostile_text,
)
json_values = st.recursive(
    json_scalars,
    lambda inner: st.one_of(
        st.lists(inner, max_size=3), st.dictionaries(hostile_text, inner, max_size=3)
    ),
    max_leaves=8,
)
arguments = st.dictionaries(hostile_text, json_values, max_size=4)

OPEN_TOOL = re.compile(r"<\s*tool_output", re.IGNORECASE)
CLOSE_TOOL = re.compile(r"<\s*/\s*tool_output", re.IGNORECASE)
OPEN_ARTIFACT = re.compile(r"<\s*artifact", re.IGNORECASE)
CLOSE_ARTIFACT = re.compile(r"<\s*/\s*artifact", re.IGNORECASE)
TOOL_HEADER = re.compile(r'<tool_output index="(\d+)" name="([^"<]*)" arguments="([^"<]*)">\n')
ARTIFACT_HEADER = re.compile(
    r'<artifact location="([^"<]*)"(?: name="([^"<]*)")? source="([^"<]*)"'
    r'(?: from_tool="([^"<]*)")?( complete="false")?>\n'
)


def tag_counts(rendered: str) -> tuple[int, int, int, int]:
    """Opening and closing <tool_output> and <artifact> tags, as a model would read them."""
    return (
        len(OPEN_TOOL.findall(rendered)),
        len(CLOSE_TOOL.findall(rendered)),
        len(OPEN_ARTIFACT.findall(rendered)),
        len(CLOSE_ARTIFACT.findall(rendered)),
    )


@given(st.integers(min_value=0), hostile_text, arguments, hostile_text)
def test_a_tool_block_has_exactly_one_open_and_one_close_tag(index, name, args, output):
    rendered = evidence_block(index, name, args, output)
    assert tag_counts(rendered) == (1, 1, 0, 0)
    assert rendered.endswith("\n</tool_output>")


@given(st.integers(min_value=0), hostile_text, arguments, hostile_text)
def test_tool_attributes_round_trip_and_cannot_break_out(index, name, args, output):
    rendered = evidence_block(index, name, args, output)
    header = TOOL_HEADER.match(rendered)
    assert header is not None
    assert int(header.group(1)) == index
    assert html.unescape(header.group(2)) == name
    assert json.loads(html.unescape(header.group(3))) == args
    assert rendered[header.end() : -len("\n</tool_output>")] == escape_block_tags(output)


@given(
    hostile_text,
    hostile_text,
    st.none() | hostile_text,
    st.sampled_from(["tool_output", "retrieved_file"]),
    st.none() | hostile_text,
    st.booleans(),
)
def test_an_artifact_block_has_one_of_each_tag_and_intact_attributes(
    location, text, name, source, from_tool, complete
):
    rendered = artifact_block(
        location, text, name=name, source=source, from_tool=from_tool, complete=complete
    )
    assert tag_counts(rendered) == (0, 0, 1, 1)
    header = ARTIFACT_HEADER.match(rendered)
    assert header is not None
    attributes = [None if value is None else html.unescape(value) for value in header.groups()]
    assert attributes[:4] == [location, name, source, from_tool]
    assert (attributes[4] is None) == complete
    assert rendered[header.end() : -len("\n</artifact>")] == escape_block_tags(text)


@given(hostile_text)
def test_escaped_text_contains_no_block_tag_and_only_gains_entities(text):
    escaped = escape_block_tags(text)
    assert tag_counts(escaped) == (0, 0, 0, 0)
    assert escape_block_tags(escaped) == escaped
    assert escaped.replace("&lt;", "<") == text.replace("&lt;", "<")
