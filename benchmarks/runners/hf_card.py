"""Generate the Hugging Face dataset card (`README.md`) from the export's manifest."""

from __future__ import annotations

import yaml

from bench_cases import CHECKS, SPLITS, CheckName
from hf_card_text import (
    BENCHMARK_README_URL,
    CASE_FORMAT,
    CONTACT,
    GUIDELINES_URL,
    INTRO,
    LABEL_MEANINGS,
    OPEN_QUESTIONS,
    SPLITS_TEXT,
    loading_text,
)
from hf_manifest import Manifest
from hf_origins import (
    ATTEST_BIBTEX,
    DATA_HUB_LICENCE,
    DATA_LICENCE,
    ORIGINS,
    licence_name,
    notice_name,
)

PRETTY_NAME = "attest benchmark: labelled agent runs"
TAGS = (
    "agent-evaluation",
    "llm-evaluation",
    "hallucination-detection",
    "prompt-injection",
    "tool-use",
    "ai-agents",
)


def revision_tag(dataset_version: str) -> str:
    """The Hub tag that pins the revision holding one dataset version."""
    return f"dv-{dataset_version[:12]}"


def render_card(manifest: Manifest) -> str:
    sections = [
        f"# {PRETTY_NAME}",
        INTRO,
        _status(manifest),
        "## Case format\n\n" + CASE_FORMAT,
        "## Splits\n\n" + SPLITS_TEXT,
        _counts(manifest),
        _labels(),
        _loading(manifest),
        _provenance(manifest),
        _citation(manifest),
        "## Contact\n\n" + CONTACT,
    ]
    return f"---\n{front_matter(manifest)}---\n\n" + "\n\n".join(sections) + "\n"


def front_matter(manifest: Manifest) -> str:
    """The card's YAML header. A check with no cases gets no config, since a config must list
    at least one data file."""
    configs = [_config(manifest, check) for check in CHECKS if manifest.check_total(check)]
    header: dict[str, object] = {
        "pretty_name": PRETTY_NAME,
        "license": hub_licences(manifest),
        "language": ["en"],
        "size_categories": [_size_category(manifest.total())],
        "task_categories": ["text-classification"],
        "tags": list(TAGS),
        "configs": configs,
    }
    return yaml.safe_dump(header, sort_keys=False, allow_unicode=True, width=1000)


def hub_licences(manifest: Manifest) -> list[str]:
    """Every licence in the export as Hugging Face identifiers: the benchmark's own licence,
    which covers the labels, notes and conversion on every case, then each upstream licence."""
    found = [DATA_HUB_LICENCE]
    for origin in manifest.origins():
        if (licence := ORIGINS[origin].hub_licence) not in found:
            found.append(licence)
    return found


def _config(manifest: Manifest, check: CheckName) -> dict[str, object]:
    files = [
        {"split": split, "path": path}
        for split in SPLITS
        if (path := manifest.data_file(check, split)) is not None
    ]
    return {"config_name": check, "data_files": files}


def _size_category(total: int) -> str:
    return "n<1K" if total < 1000 else "1K<n<10K" if total < 10_000 else "10K<n<100K"


def _status(manifest: Manifest) -> str:
    drafts, total = manifest.label_status.get("draft", 0), manifest.total()
    share = (
        "All labels are" if drafts == total else f"{drafts} of {total} cases have labels that are"
    )
    questions = "\n".join(f"- {question}" for question in OPEN_QUESTIONS)
    return f"""## Status: draft labels

> **{share} DRAFTS.** They were written by the people who wrote or converted each case and
> have not yet been confirmed by two independent annotators. **Do not report any number
> computed on this dataset as attest's accuracy** (or any other system's) until the labels are
> confirmed; for now, results only show that an evaluation pipeline runs.

The [labelling guidelines]({GUIDELINES_URL}) are a draft too. These questions in them are
still open, and answering them may change labels:

{questions}

This export is dataset version `{manifest.dataset_version}`, the same value attest's benchmark
reports carry as `dataset_version`, so a published report can be matched to the revision tagged
`{revision_tag(manifest.dataset_version)}` here. Built from attest commit
`{manifest.attest_commit or "unknown"}`; export format version {manifest.format_version}."""


def _counts(manifest: Manifest) -> str:
    head = "| | " + " | ".join(SPLITS) + " | total |\n|---|" + "---:|" * (len(SPLITS) + 1)
    by_check = [
        f"| `{check}` | "
        + " | ".join(str(manifest.split_total(check, split)) for split in SPLITS)
        + f" | {manifest.check_total(check)} |"
        for check in CHECKS
    ]
    by_origin = [
        f"| `{origin}` | "
        + " | ".join(str(manifest.origin_split_total(origin, split)) for split in SPLITS)
        + f" | {sum(manifest.origin_split_total(origin, split) for split in SPLITS)} |"
        for origin in manifest.origins()
    ]
    return "\n".join(
        [
            f"## Counts\n\n{manifest.total()} cases. By check and split:\n",
            head,
            *by_check,
            "\nBy origin and split, all checks together:\n",
            head,
            *by_origin,
        ]
    )


def _labels() -> str:
    rows = [
        f"| `{check}` | {unit} | {meaning} |" for check, (unit, meaning) in LABEL_MEANINGS.items()
    ]
    return "\n".join(
        [
            '## Labels\n\n<a id="labels"></a>\n',
            "| Check | Labelled unit | Labels |\n|---|---|---|",
            *rows,
            f"\nThe [guidelines]({GUIDELINES_URL}) define each label with edge cases, and the "
            f"[benchmark README]({BENCHMARK_README_URL}) explains how attest's predictions are "
            "scored against them.",
        ]
    )


def _loading(manifest: Manifest) -> str:
    return loading_text(manifest.hf_repo, revision_tag(manifest.dataset_version))


def _provenance(manifest: Manifest) -> str:
    blocks = ['## Provenance and licences\n\n<a id="licenses"></a>']
    for origin in manifest.origins():
        info = ORIGINS[origin]
        lines = [f"### {info.title} (`{origin}`)\n", info.description, ""]
        if info.upstream_url is not None:
            lines.append(f"- Upstream: {info.upstream_url} at commit `{info.upstream_commit}`")
            lines.append(f"- What was selected, stripped and why: [SOURCE.md]({info.source_link})")
        licence_file = f"`LICENSES/{licence_name(origin)}`"
        if info.upstream_url is None:
            lines.append(f"- Licence: {info.licence}, see {licence_file}")
        else:
            lines.append(f"- Upstream run content: {info.licence}, full text in {licence_file}")
            lines.append(f"- Labels, notes and conversion: {DATA_LICENCE}")
        if info.notice_file is not None:
            lines.append(f"- Notice: `LICENSES/{notice_name(origin)}`")
        blocks.append("\n".join(lines))
    upstream = sorted({ORIGINS[o].licence for o in manifest.origins()} - {DATA_LICENCE})
    blocks.append(
        f"The benchmark's own data is licensed {DATA_LICENCE}: the attest seed cases, and the "
        "labels, notes and conversion work on every case, converted ones included. The "
        "upstream run content of a converted case keeps its upstream "
        f"licence ({', '.join(upstream) or 'none in this export'}), as listed for each origin "
        f"above; the card's `license` field lists all of them. The {DATA_LICENCE} notice is "
        "`LICENSES/attest-seed.txt`; the upstream licence and notice files are copied "
        "verbatim from the repository. attest's code is separately licensed AGPL-3.0 and is "
        "not part of this dataset."
    )
    return "\n\n".join(blocks)


def _citation(manifest: Manifest) -> str:
    entries = [ORIGINS[o].bibtex for o in manifest.origins() if ORIGINS[o].bibtex is not None]
    upstream = "\n\n".join(f"```bibtex\n{entry}\n```" for entry in entries)
    return (
        f"## Citation\n\nattest:\n\n```bibtex\n{ATTEST_BIBTEX}\n```\n\n"
        "If you use the converted cases, please also cite the upstream benchmarks (entries "
        f"copied from each upstream README):\n\n{upstream}"
    )
