from __future__ import annotations

EXTRACT_SYSTEM = (
    "You split an AI agent's final answer into atomic factual claims to fact-check. "
    "Each claim must be a single, self-contained, independently-checkable statement. "
    "Consolidate: do NOT split one fact into several near-duplicate sub-claims, do NOT "
    "emit every sentence or clause, and merge overlapping points into one claim. Drop "
    "hedges, opinions, filler, questions, and generic advice. Keep only distinct, "
    "verifiable assertions of fact, and prefer a short list of meaningful claims over a "
    "long list of fragments. Preserve the original meaning; add nothing."
)


VERIFY_SYSTEM = {
    "factual": (
        "You are a strict fact-checker. Decide whether the EVIDENCE supports the CLAIM, "
        "using ONLY the evidence — no outside knowledge, no assumptions.\n"
        "- supported: the evidence directly entails the claim.\n"
        "- unsupported: the evidence contradicts the claim.\n"
        "- unverifiable: the evidence is silent or unrelated, so it cannot be judged.\n"
        "Give a clear, complete reason for your verdict, and quote the exact deciding "
        "span from the evidence. Watch direction and magnitude carefully (e.g. 'X is "
        "larger than Y' is unsupported if the evidence shows Y is larger)."
    ),
    "plan": (
        "The answer being checked is a PLAN or recommendation, NOT a report of completed "
        "work. Decide whether the CLAIM faithfully reflects the plan in the EVIDENCE, using "
        "ONLY the evidence.\n"
        "- supported: the plan states or directly implies the claim (treat 'X will intercept "
        "requests' / 'the plan covers X' as supported if the plan describes X — even though "
        "nothing has run yet).\n"
        "- unsupported: the plan contradicts the claim.\n"
        "- unverifiable: the plan is silent on it.\n"
        "Do NOT require runtime proof; judge fidelity to the plan. Give a clear reason and "
        "quote the deciding span from the plan."
    ),
}


BATCH_INSTRUCTION = (
    "You are given several NUMBERED claims and one EVIDENCE block. Apply the standard below "
    "to EACH claim independently, using ONLY the evidence. Return exactly one verdict per "
    "claim: its number, the verdict, a brief reason, and the deciding span from the evidence. "
    "Do not skip or merge claims.\n\nSTANDARD:\n"
)


def verify_system(answer_kind: str) -> str:
    return VERIFY_SYSTEM.get(answer_kind, VERIFY_SYSTEM["factual"])


def batch_system(answer_kind: str) -> str:
    return BATCH_INSTRUCTION + verify_system(answer_kind)


def extract_user(final_answer: str) -> str:
    return f"Final answer to decompose:\n\n{final_answer}"


def verify_user(claim: str, evidence: str) -> str:
    return f"CLAIM:\n{claim}\n\nEVIDENCE (the agent's real tool outputs):\n{evidence}"


def evidence_prefix(evidence: str) -> str:
    return f"EVIDENCE (the agent's real tool outputs):\n{evidence}"


def claims_user(claims: list[str]) -> str:
    numbered = "\n".join(f"{i}. {claim}" for i, claim in enumerate(claims, start=1))
    return f"CLAIMS:\n{numbered}"
