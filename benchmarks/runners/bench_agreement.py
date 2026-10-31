"""How far two annotators agree, per check and kind of label: agreement and Cohen's kappa."""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel

from bench_annotations import Annotations, Dimension, label_items
from bench_cases import CHECKS, Case, CheckName

KAPPA_THRESHOLD = 0.6
"""Below this on a check, the guidelines are unclear for it: fix them before adding cases."""


class Disagreement(BaseModel):
    case_id: str
    check: CheckName
    dimension: Dimension
    subject: str
    labels: dict[str, str]
    """Annotator -> their label."""


class DimensionAgreement(BaseModel):
    """Agreement on one kind of label in one check, over every item both annotators labelled."""

    check: CheckName
    dimension: Dimension
    cases: int
    items: int
    agreed: int
    observed: float
    kappa: float | None
    """None when kappa is undefined: both annotators gave one and the same label throughout."""
    low_confidence_cases: int
    ambiguous_cases: int

    @property
    def below_threshold(self) -> bool:
        return self.kappa is not None and self.kappa < KAPPA_THRESHOLD


class AgreementReport(BaseModel):
    annotators: tuple[str, str]
    cases_compared: int
    only_one_annotator: list[str]
    """Case ids that only one of the two has labelled; they aren't in the numbers."""
    dimensions: list[DimensionAgreement]
    disagreements: list[Disagreement]
    kappa_threshold: float = KAPPA_THRESHOLD


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa for two raters' labels on the same items; None when it is undefined."""
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    first = Counter(a for a, _ in pairs)
    second = Counter(b for _, b in pairs)
    chance = sum(first[label] * second[label] for label in first) / (n * n)
    if chance == 1.0:
        return None
    return (observed - chance) / (1.0 - chance)


def agreement(
    annotations: Annotations, cases: dict[str, Case], first: str, second: str
) -> AgreementReport:
    """Compare two annotators over the cases both have labelled."""
    for name in (first, second):
        if name not in annotations:
            raise ValueError(f"no labels from annotator {name!r}")
    a, b = annotations[first], annotations[second]
    shared = sorted(set(a) & set(b))
    pairs: dict[tuple[CheckName, Dimension], list[tuple[str, str]]] = {}
    case_sets: dict[tuple[CheckName, Dimension], set[str]] = {}
    disagreements: list[Disagreement] = []
    for case_id in shared:
        check = cases[case_id].check
        left, right = label_items(a[case_id].labels), label_items(b[case_id].labels)
        for key in sorted(left):
            group = (check, key[0])
            pairs.setdefault(group, []).append((left[key], right[key]))
            case_sets.setdefault(group, set()).add(case_id)
            if left[key] != right[key]:
                disagreements.append(
                    Disagreement(
                        case_id=case_id,
                        check=check,
                        dimension=key[0],
                        subject=key[1],
                        labels={first: left[key], second: right[key]},
                    )
                )
    dimensions = [
        _dimension(group, pairs[group], case_sets[group], annotations, (first, second))
        for group in sorted(pairs, key=lambda g: (CHECKS.index(g[0]), g[1]))
    ]
    return AgreementReport(
        annotators=(first, second),
        cases_compared=len(shared),
        only_one_annotator=sorted(set(a) ^ set(b)),
        dimensions=dimensions,
        disagreements=disagreements,
    )


def _dimension(
    group: tuple[CheckName, Dimension],
    pairs: list[tuple[str, str]],
    case_ids: set[str],
    annotations: Annotations,
    names: tuple[str, str],
) -> DimensionAgreement:
    agreed = sum(x == y for x, y in pairs)
    mine = [annotations[name][case_id] for name in names for case_id in case_ids]
    return DimensionAgreement(
        check=group[0],
        dimension=group[1],
        cases=len(case_ids),
        items=len(pairs),
        agreed=agreed,
        observed=agreed / len(pairs),
        kappa=cohen_kappa(pairs),
        low_confidence_cases=len({x.case_id for x in mine if x.confidence == "low"}),
        ambiguous_cases=len({x.case_id for x in mine if x.ambiguous}),
    )


def markdown(report: AgreementReport) -> str:
    first, second = report.annotators
    lines = [
        f"# Agreement: {first} vs {second}",
        "",
        f"{report.cases_compared} cases labelled by both. Kappa below "
        f"{report.kappa_threshold} means the guidelines are unclear for that check.",
        "",
        "| Check | Label | Cases | Items | Agreement | Kappa | Low confidence | Ambiguous |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for d in report.dimensions:
        kappa = "n/a" if d.kappa is None else f"{d.kappa:.2f}" + (" ⚠" if d.below_threshold else "")
        lines.append(
            f"| {d.check} | {d.dimension} | {d.cases} | {d.items} | "
            f"{d.observed:.0%} {d.agreed}/{d.items} | {kappa} | "
            f"{d.low_confidence_cases} | {d.ambiguous_cases} |"
        )
    if report.only_one_annotator:
        lines += ["", f"Labelled by only one: {', '.join(report.only_one_annotator)}"]
    if report.disagreements:
        lines += ["", "## Disagreements", ""]
        for x in report.disagreements:
            lines.append(
                f"- `{x.case_id}` {x.dimension} {x.subject!r}: "
                f"{first} `{x.labels[first]}`, {second} `{x.labels[second]}`"
            )
    return "\n".join(lines) + "\n"
