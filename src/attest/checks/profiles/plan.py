"""Plan answer kind: claims are checked for fidelity to a plan, not runtime proof."""

from .factual import EXTRACT_PROMPT

VERIFY_PROMPT = (
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
)

__all__ = ["EXTRACT_PROMPT", "VERIFY_PROMPT"]
