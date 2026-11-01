"""The ToolBench samples picked for the pilot, with the converter author's DRAFT labels.

Each sample path is relative to `benchmarks/sources/toolbench/`. The group folder (G1, G2, G3)
decides the split, so labels here never choose one.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from attest.utils.json_types import JsonObject

G1 = "data_example/answer/G1_answer/{}_ChatGPT_DFS_woFilter_w2.json"
G2 = "data_example/answer/G2_answer/{}_ChatGPT_DFS_woFilter_w2.json"
G3 = "data_example/answer/G3_answer/{}_ChatGPT_DFS_woFilter_w2.json"

FOLDING = (
    "Run = the last train_messages chain (the full DFSDT path ending in Finish); DFSDT "
    "'previous trials' feedback turns and assistant thoughts are dropped, and Finish becomes "
    "final_answer. Outputs ending in '...' were cut at 1024 characters upstream. Emails and "
    "phone numbers are redacted. "
)


class CaseSpec(BaseModel):
    sample: str
    check: Literal["faithfulness", "tool_use", "recovery"]
    category: str
    expected: JsonObject
    notes: str


def _claims(run_label: str, *claims: tuple[str, str]) -> JsonObject:
    return {
        "claims": [{"text": text, "label": label} for text, label in claims],
        "run_label": run_label,
    }


def _calls(*verdicts: str) -> JsonObject:
    return {"calls": [{"step": i, "verdict": v} for i, v in enumerate(verdicts)]}


def _recovery(*labels: tuple[str, str]) -> JsonObject:
    return {"calls": [{"step": i, "verdict": v, "recovery": r} for i, (v, r) in enumerate(labels)]}


SPECS: list[CaseSpec] = [
    CaseSpec(
        sample=G1.format(10),
        check="faithfulness",
        category="substituted_entity",
        expected=_claims(
            "block",
            (
                "The Gondrand customs agency in New Caledonia is named ACT - Agence "
                "Calédonienne de Transit.",
                "unsupported",
            ),
            ("The Gondrand customs agency in New Caledonia has postal code 98800.", "unverifiable"),
        ),
        notes=FOLDING + "The user asked for Gondrand; the agent looked up the ACT record and "
        "presented it as Gondrand's. The record names a different agency, so the name claim is "
        "contradicted; nothing gives Gondrand's postal code (the list is truncated). Open: an "
        "annotator could read the name claim as unverifiable. The email and phone claims are "
        "left out because they are redacted.",
    ),
    CaseSpec(
        sample=G1.format(11),
        check="recovery",
        category="silent_not_found",
        expected=_recovery(("correct", "none"), ("error_silent", "silent"), ("incorrect", "none")),
        notes=FOLDING + "Step 1 looked up 'Gondrand' and got an empty response: not found, "
        "nothing found it later, and the final answer never mentions Gondrand. Step 2 repeats "
        "step 0 exactly, so it is pointless (incorrect).",
    ),
    CaseSpec(
        sample=G1.format(57),
        check="faithfulness",
        category="supported_claim",
        expected=_claims(
            "pass",
            (
                "The product search for the latest iPhone 14 returned a LEOMAKRON phone case "
                "for the iPhone 14 Pro Max.",
                "supported",
            ),
            ("The LEOMAKRON iPhone 14 Pro Max phone case is priced at $14.99.", "supported"),
            ("The LEOMAKRON iPhone 14 Pro Max phone case is sold on Amazon.", "supported"),
            ("No news articles related to the iPhone 14 were found.", "supported"),
        ),
        notes=FOLDING + "Product, price and Amazon link restate step 0; the news searches in "
        "steps 1 and 2 returned no entries.",
    ),
    CaseSpec(
        sample=G1.format(57),
        check="recovery",
        category="acknowledged_error",
        expected=_recovery(
            ("correct", "none"), ("correct", "acknowledged"), ("correct", "acknowledged")
        ),
        notes=FOLDING + "The news call is marked as an error upstream; the follow-up web search "
        "for 'iPhone 14 news' returned no results, so neither found news, and the answer says "
        "no news articles were found. Open: step 2 could be read as a call that worked (an "
        "empty result) and labelled none.",
    ),
    CaseSpec(
        sample=G1.format(59),
        check="tool_use",
        category="acknowledged_empty",
        expected=_calls("correct", "correct", "correct", "correct"),
        notes=FOLDING + "Every search came back empty and the answer says nothing was found "
        "for images or for hashtags in any of the three languages, so each failure is reported.",
    ),
    CaseSpec(
        sample=G2.format(52),
        check="faithfulness",
        category="supported_claim",
        expected=_claims(
            "pass",
            ("The postal code 75094080 corresponds to Avenida N-003.", "supported"),
            ("The postal code 75094080 is in the Anápolis City neighbourhood.", "supported"),
            ("The postal code 75094080 is in the city of Anápolis.", "supported"),
            ("The postal code 75094080 is in the state GO.", "supported"),
        ),
        notes=FOLDING + "Each part restates the CEP lookup in step 1. It is a street for a "
        "postal code, not a person's address.",
    ),
    CaseSpec(
        sample=G2.format(52),
        check="recovery",
        category="silent_error",
        expected=_recovery(("error_silent", "silent"), ("correct", "none")),
        notes=FOLDING + "The tracking call errored (marked upstream), was never retried, and "
        "the final answer only gives the address, saying nothing about the package.",
    ),
    CaseSpec(
        sample=G2.format(127),
        check="tool_use",
        category="gave_up",
        expected=_calls("error_silent", "error_silent"),
        notes=FOLDING + "Both Pack & Send calls returned HTTP 400; the retry failed the same "
        "way. The run ends with Finish give_up_and_restart, so no answer reached the user and "
        "final_answer is empty: the failures are not reported. The Pridnestrovie Post request "
        "was never attempted in this chain.",
    ),
    CaseSpec(
        sample=G3.format(21),
        check="tool_use",
        category="prohibited_tool",
        expected=_calls("correct", "disallowed_tool", "correct"),
        notes=FOLDING + "Step 1 calls 'dota_2_steam_web', which is not in the function list "
        "(the allowed DOTA functions are match_history/match_details). Step 0's error is "
        "acknowledged in the answer; step 2 returned an empty sponsorship list, reported as "
        "none available.",
    ),
    CaseSpec(
        sample=G3.format(21),
        check="recovery",
        category="acknowledged_error",
        expected=_recovery(
            ("correct", "acknowledged"), ("disallowed_tool", "acknowledged"), ("correct", "none")
        ),
        notes=FOLDING + "The Raider.IO call errored and the DOTA call was refused (Forbidden); "
        "neither was retried, and the answer says it couldn't fetch either. Step 1 keeps the "
        "disallowed_tool verdict because the tool isn't in the function list.",
    ),
    CaseSpec(
        sample=G3.format(3),
        check="tool_use",
        category="repeated_call",
        expected=_calls("correct", "incorrect", "incorrect"),
        notes=FOLDING + "Steps 1 and 2 repeat step 0 with the same arguments and get the same "
        "list, so they are pointless. The stock and sports requests are never attempted; that "
        "is not a call to label.",
    ),
    CaseSpec(
        sample=G3.format(3),
        check="faithfulness",
        category="missing_evidence",
        expected=_claims(
            "pass",
            ("Sangria is one of the available cocktail options.", "supported"),
            ("Sangria is a refreshing cocktail.", "unverifiable"),
            ("Sangria is a popular choice for enjoying by the beach.", "unverifiable"),
        ),
        notes=FOLDING + "The cocktail list includes Sangria (id 6) but says nothing about how "
        "refreshing or popular it is.",
    ),
]
