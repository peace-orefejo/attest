from __future__ import annotations

EXTRACT_PROMPT = (
    "You split an AI agent's final answer into atomic factual claims to fact-check. "
    "Each claim must be a single, self-contained, independently-checkable statement. "
    "Consolidate: do NOT split one fact into several near-duplicate sub-claims, do NOT "
    "emit every sentence or clause, and merge overlapping points into one claim. Drop "
    "hedges, opinions, filler, questions, and generic advice. Keep only distinct, "
    "verifiable assertions of fact, and prefer a short list of meaningful claims over a "
    "long list of fragments. Always keep the answer's bottom line, its direct answer to the "
    "task, as its own claim worded as the answer asserts it. Never fold a conclusion into "
    "the reasoning given for it, and never narrow or reframe a claim to fit that reasoning "
    "(e.g. do not turn 'A is cheaper than B' into 'A is cheaper than B per unit'); extract "
    "the reasoning as separate claims. When a task is given, use it only to make claims "
    "self-contained (e.g. if the task asks which is cheaper to run, write 'A costs less to "
    "run than B', not 'A is better'); never take claims from the task itself. Preserve "
    "the original meaning; add nothing."
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
