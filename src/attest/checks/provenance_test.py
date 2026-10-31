"""Findings point at the one evidence block their quote came from."""

from attest.checks.provenance import with_locations
from attest.results import Finding, Severity
from attest.trajectory import EvidenceBlock


def _block(location: str, text: str) -> EvidenceBlock:
    return EvidenceBlock(location=location, text=text, rendered=text)


def _finding(quote: str | None) -> Finding:
    return Finding(severity=Severity.PASS, verdict="supported", subject="c", evidence=quote)


BLOCKS = [
    _block("steps[0].tool_call.output", "Paris: 2,103,000\nsee <tool_output> docs"),
    _block("artifacts[0]", "Paris is the capital."),
]


def test_a_quote_found_in_one_block_gets_its_location():
    [located] = with_locations([_finding("PARIS:   2,103,000")], BLOCKS)
    assert located.metadata == {"location": "steps[0].tool_call.output"}


def test_a_quote_copied_from_the_escaped_rendering_still_matches():
    [located] = with_locations([_finding("see &lt;tool_output> docs")], BLOCKS)
    assert located.metadata["location"] == "steps[0].tool_call.output"


def test_ambiguous_or_missing_quotes_get_no_location():
    findings = [_finding("Paris"), _finding("Berlin"), _finding(None), _finding("  ")]
    assert all(f.metadata == {} for f in with_locations(findings, BLOCKS))
