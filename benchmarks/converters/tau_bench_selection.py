"""Every τ-bench run picked for the pilot, with the converter author's draft labels."""

from __future__ import annotations

from tau_bench_airline_cases import AIRLINE_CASES
from tau_bench_retail_cases import RETAIL_CASES
from tau_bench_spec import CaseSpec

CASES: list[CaseSpec] = [*RETAIL_CASES, *AIRLINE_CASES]
