from __future__ import annotations

BATCH_INSTRUCTION = (
    "You are given several NUMBERED claims and one EVIDENCE block. Apply the standard below "
    "to EACH claim independently, using ONLY the evidence. Return exactly one verdict per "
    "claim: its number, the verdict, a brief reason, and the deciding span from the evidence. "
    "Do not skip or merge claims.\n\nSTANDARD:\n"
)


def batch_system(verify_prompt: str) -> str:
    return BATCH_INSTRUCTION + verify_prompt


def extract_user(final_answer: str, task: str | None = None) -> str:
    context = (
        f"Task the answer responds to (context only, do not extract claims from it):\n{task}\n\n"
        if task and task.strip()
        else ""
    )
    return f"{context}Final answer to decompose:\n\n{final_answer}"


def verify_user(claim: str, evidence: str) -> str:
    return f"CLAIM:\n{claim}\n\nEVIDENCE (the agent's real tool outputs):\n{evidence}"


def evidence_prefix(evidence: str) -> str:
    return f"EVIDENCE (the agent's real tool outputs):\n{evidence}"


def claims_user(claims: list[str]) -> str:
    numbered = "\n".join(f"{i}. {claim}" for i, claim in enumerate(claims, start=1))
    return f"CLAIMS:\n{numbered}"
