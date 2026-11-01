"""Withhold case contents from reports on private datasets, keeping every metric.

This pseudonymises; it doesn't anonymise. Case ids are hashed, so anyone who can guess an id
can confirm it by hashing it, unless `ID_KEY_ENV` holds a secret key: then the hash is keyed
(HMAC-SHA256) and can't be checked without the key. Categories, origins, labels, predictions,
timings and usage stay in the report: each row keeps its `origin`, `per_origin` breaks every
check down by it and the summary counts cases by it. Origin and category names are chosen by
the dataset's owner and are reported as written, so owners should choose neutral names that
don't name a customer or person.
"""

from __future__ import annotations

import hashlib
import hmac
import os

from bench_rows import CaseRow

WITHHELD_ERROR = "error (details withheld: private dataset)"
ID_KEY_ENV = "ATTEST_BENCH_ID_KEY"


def withhold_case_details(rows: list[CaseRow], key: bytes | None = None) -> list[CaseRow]:
    """Replace what could reveal a private case: its id, item keys (such as claim texts) and
    error messages. Labels, predictions, categories, timings and usage stay, so the report's
    metrics are unchanged and each row can still be matched across runs of the same dataset.
    """
    return [_withhold(row, key) for row in rows]


def id_key_from_env() -> bytes | None:
    value = os.environ.get(ID_KEY_ENV, "")
    return value.encode() if value else None


def key_fingerprint(key: bytes | None) -> str | None:
    """Identifies a key without revealing it, so reports keyed differently aren't compared."""
    if key is None:
        return None
    return hmac.new(key, b"attest benchmark case-id key", hashlib.sha256).hexdigest()[:12]


def private_case_id(case_id: str, key: bytes | None = None) -> str:
    """A stable pseudonym for `case_id`; keyed with HMAC-SHA256 when `key` is given."""
    if key is None:
        return "case-" + hashlib.sha256(case_id.encode()).hexdigest()[:12]
    return "case-" + hmac.new(key, case_id.encode(), hashlib.sha256).hexdigest()[:16]


def _withhold(row: CaseRow, key: bytes | None) -> CaseRow:
    items = [
        item.model_copy(update={"key": f"item-{number}"})
        for number, item in enumerate(row.items, start=1)
    ]
    return row.model_copy(
        update={
            "id": private_case_id(row.id, key),
            "items": items,
            "error": WITHHELD_ERROR if row.error is not None else None,
        }
    )
