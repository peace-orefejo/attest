from attest.code_review.guidelines.evidence import fit_evidence

BLOCK = '<tool_output index="{i}">\n{body}\n</tool_output>'
EVIDENCE = "\n".join(BLOCK.format(i=i, body=ch * 50) for i, ch in enumerate("xy"))


def test_evidence_within_the_limit_is_unchanged():
    assert fit_evidence(EVIDENCE, len(EVIDENCE)) == EVIDENCE


def test_evidence_is_cut_after_the_last_whole_block():
    first = BLOCK.format(i=0, body="x" * 50)
    assert fit_evidence(EVIDENCE, len(first) + 5) == first


def test_a_first_block_too_big_to_fit_is_cut_and_closed():
    cut = fit_evidence(EVIDENCE, 40)
    assert len(cut) <= 40
    assert cut.endswith("\n</tool_output>")
    assert cut.count("<tool_output") == 1
