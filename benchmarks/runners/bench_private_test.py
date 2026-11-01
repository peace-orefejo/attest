from __future__ import annotations

import pytest

from bench_private import (
    ID_KEY_ENV,
    WITHHELD_ERROR,
    id_key_from_env,
    private_case_id,
    withhold_case_details,
)
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


def test_a_key_makes_ids_uncheckable_without_it() -> None:
    plain = private_case_id("vera-refund-42")
    keyed = private_case_id("vera-refund-42", b"secret")
    assert keyed != plain and keyed == private_case_id("vera-refund-42", b"secret")
    assert keyed != private_case_id("vera-refund-42", b"other")
    [row] = withhold_case_details([_row()], b"secret")
    assert row.id == keyed


@pytest.mark.parametrize(
    ("value", "warned"),
    [
        ("x", "1 characters long, shorter than 32"),
        ("correct horse battery", "shorter than 32"),
        ("ab" * 20, "only 2 distinct"),
        ("0123456" * 6, "only 7 distinct"),
        ("4f9c2a7e1b8d3f60a5c7e9b2d4f6a8c1", None),
    ],
)
def test_a_weak_key_is_used_with_a_warning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    value: str,
    warned: str | None,
) -> None:
    monkeypatch.setenv(ID_KEY_ENV, value)
    assert id_key_from_env() == value.encode()
    err = capsys.readouterr().err
    if warned is None:
        assert err == ""
    else:
        assert f"warning: {ID_KEY_ENV}" in err and warned in err and "openssl rand" in err


def test_no_key_means_no_hmac_and_no_weak_key_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(ID_KEY_ENV, raising=False)
    assert id_key_from_env() is None
    assert capsys.readouterr().err == ""
