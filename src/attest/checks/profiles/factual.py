"""Factual answer kind: claims are checked strictly against the evidence."""

EXTRACT_PROMPT = (
    "You split an AI agent's final answer into atomic factual claims to fact-check. "
    "Each claim must be a single, self-contained, independently-checkable statement. "
    "Consolidate: do NOT split one fact into several near-duplicate sub-claims, do NOT "
    "emit every sentence or clause, and merge overlapping points into one claim. Drop "
    "hedges, opinions, filler, questions, and generic advice. Keep only distinct, "
    "verifiable assertions of fact, and prefer a short list of meaningful claims over a "
    "long list of fragments. Preserve the original meaning; add nothing."
)

VERIFY_PROMPT = (
    "You are a strict fact-checker. Decide whether the EVIDENCE supports the CLAIM, "
    "using ONLY the evidence — no outside knowledge, no assumptions.\n"
    "- supported: the evidence directly entails the claim.\n"
    "- unsupported: the evidence contradicts the claim.\n"
    "- unverifiable: the evidence is silent or unrelated, so it cannot be judged.\n"
    "Give a clear, complete reason for your verdict, and quote the exact deciding "
    "span from the evidence. Watch direction and magnitude carefully (e.g. 'X is "
    "larger than Y' is unsupported if the evidence shows Y is larger)."
)
