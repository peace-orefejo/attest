from __future__ import annotations

from bench_private import WITHHELD_ERROR, private_case_id, withhold_case_details
from bench_rows import CaseRow, item


def _row(**overrides: object) -> CaseRow:
    fields: dict[str, object] = {
        "id": "vera-refund-42",
        "check": "faithfulness",
        "category": "c",
        "source": "real",
        "label_status": "draft",
        "items": [
            item("The refund was $40.", "supported", "supported"),
            item("It was sent to Ada.", "unsupported", "supported"),
        ],
        "correct": False,
        "latency_s": 0.2,
    }
    fields.update(overrides)
    return CaseRow.model_validate(fields)


def test_withholding_hides_ids_claims_and_errors_but_keeps_outcomes() -> None:
    original = _row(status="errored", error="Ada's card ending 4242 was declined")
    [row] = withhold_case_details([original])

    assert row.id == private_case_id("vera-refund-42") and row.id.startswith("case-")
    assert [i.key for i in row.items] == ["item-1", "item-2"]
    assert row.error == WITHHELD_ERROR
    dumped = row.model_dump_json()
    assert "vera" not in dumped and "Ada" not in dumped and "4242" not in dumped
    assert [(i.expected, i.predicted, i.correct) for i in row.items] == [
        (i.expected, i.predicted, i.correct) for i in original.items
    ]
    assert row.correct == original.correct and row.status == original.status


def test_private_ids_are_stable_and_errorless_rows_stay_errorless() -> None:
    assert private_case_id("a") == private_case_id("a") != private_case_id("b")
    [row] = withhold_case_details([_row()])
    assert row.error is None
