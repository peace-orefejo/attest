---
title: "Benchmark: measuring attest's own accuracy"
description: "The labelled benchmark that will measure each attest check: per-check metrics with intervals, seed, τ-bench, AgentDojo and ToolBench cases, blind double labelling. No accuracy figures yet."
---

# Benchmark

attest grades agent runs, but how often its grades are right hasn't been measured yet. The
benchmark in [`benchmarks/`](https://github.com/peace-orefejo/attest/tree/main/benchmarks) is
how it will be measured: people label runs, attest grades the same runs, and the runner counts
where they agree and where they don't. It lives in the repository and isn't shipped in the
package.

!!! warning "No accuracy figures yet"
    Every label in the benchmark is still a draft: a proposal that hasn't been confirmed by
    blind double labelling. Until labels are confirmed, a benchmark run only shows that the
    pipeline works. attest publishes no accuracy figures, and numbers from the current data
    shouldn't be quoted as attest's accuracy.

This page is a summary. The
[benchmark README](https://github.com/peace-orefejo/attest/blob/main/benchmarks/README.md) has
the full details: the case format, every report field and every option.

## What it measures

Results are reported per check. There is no single "attest accuracy" number.

| Dataset | What attest is scored on | Unit | Labels |
|---|---|---|---|
| `faithfulness` | Each claim's verdict | claim | `supported`, `unsupported`, `unverifiable` |
| `tool_use` | Each tool call's verdict | tool call | `correct`, `disallowed_tool`, `error_silent`, `error_claimed_success`, `incorrect` |
| `recovery` | How each tool error was dealt with | tool call | `none`, `retried`, `fallback`, `acknowledged`, `silent`, `claimed_success` |
| `prompt_injection` | Whether the run carried an injection, and whether the agent acted on it | run | `none`, `payload`, `compromised` |
| `role_adherence` | The run's role verdict | run | `in_scope`, `appropriately_refused`, `out_of_scope_complied` |

Faithfulness cases supply their labelled claims directly, so the faithfulness numbers measure
attest's judgement of each claim against the evidence. They say nothing about how well attest
splits a real answer into claims.

**Binary views.** Each check keeps its full confusion matrix, and is also collapsed into
yes/no questions:

| Check | View | Positive |
|---|---|---|
| `faithfulness` | `contradiction_detection` | `unsupported` |
| `faithfulness` | `evidence_sufficiency` | `unsupported` or `unverifiable` |
| `tool_use`, `recovery`, `prompt_injection`, `role_adherence` | `violation_detection` | Any label that marks a problem |

Only `contradiction_detection` measures whether attest finds claims the evidence contradicts.
`evidence_sufficiency` measures whether it flags claims the evidence doesn't back, for any
reason.

For each view the report gives precision, recall, false-positive rate and false-negative rate,
each with a Wilson 95% interval and the counts behind it, plus F1. The sets are small, so the
intervals are wide: read the interval, not the point estimate.

**Coverage and effective accuracy.** A case is graded, errored (its evaluation raised, or a
model call inside the check failed and left part of it unchecked) or not run (the call budget
ran out). Coverage, the share of cases graded, is shown beside every figure. Graded-only
accuracy counts graded cases; effective accuracy counts every attempted case, with errored and
not-run items counted as wrong. If 65 of 70 graded cases are right and 30 more errored or
didn't run, graded-only accuracy is 92.9% but effective accuracy is 65%, at 70% coverage.

**Breakdowns.** Every metric is also given per category (the scenario, such as
`known_hallucination` or `recovered_error`) and per origin, so a report that mixes sources can
be read one source at a time.

## The dataset

| Origin | Cases | Checks | Where the runs come from |
|---|---|---|---|
| `attest-seed` | 32 | all five | A small synthetic set written for the benchmark. |
| `tau-bench` | 10 | faithfulness, tool use, recovery, role adherence | Public gpt-4o runs from [τ-bench](https://github.com/sierra-research/tau-bench). |
| `agentdojo` | 10 | prompt injection, tool use | Public runs from [AgentDojo](https://github.com/ethz-spylab/agentdojo). |
| `toolbench` | 12 | faithfulness, tool use, recovery | Upstream [ToolBench](https://github.com/OpenBMB/ToolBench) samples, with contact details redacted. |

Each external origin has a converter in `benchmarks/converters/` that regenerates its cases
from upstream files vendored in `benchmarks/sources/<origin>/`, together with the upstream
licence and a `SOURCE.md` that records the upstream commit, what was selected and what was
stripped. Anything that could act as a label, such as rewards, success flags or grader output,
is stripped before a run becomes a case.

**Licence.** The benchmark's own data and labels (the seed cases, and the labels, notes and
conversion work on every case) are licensed
[CC-BY-4.0](https://github.com/peace-orefejo/attest/blob/main/benchmarks/datasets/LICENSE).
Content converted from an upstream benchmark keeps its own licence (MIT for τ-bench and
AgentDojo, Apache-2.0 for ToolBench). The benchmark code is Apache-2.0, like the rest of attest.

**Label status.** Every case is `label_status: "draft"`. A case becomes `confirmed` only through
the double labelling below, with at least two annotators recorded.

**Splits.** Cases are split into `dev`, `validation` and `heldout`. Prompts and heuristics are
tuned against `dev` only. A change is checked against `validation` before a release, without
tuning on what it shows. `heldout` is run only for a release or a published result, and the
runner refuses it unless you pass `--heldout`.

**Task families.** Related runs, such as runs of the same upstream task or environment, share a
`task_family`, and a family may appear in only one split, across all checks. So may every
family nested under it: `tau-bench/airline/25-49` belongs with `tau-bench/airline`. The loader
rejects a case that breaks this, so related runs can't leak between splits. Editing any case
file changes the `dataset_version` (a SHA-256 of every case file), and reports on different
versions aren't compared.

### Private datasets

Runs from your own agents can hold customer data, so keep them outside the repository, in a
folder with the same layout, and pass it with `--datasets`. Reports on a private folder keep
every metric but withhold the cases' contents: case ids become hashes, claim texts become
`item-1`, `item-2` and so on, and error messages are dropped. They are marked
`dataset_visibility: "private"`, and `compare.py` won't compare them with public reports.

This is pseudonymisation, not anonymisation. Categories, origins, labels, predictions, timings
and usage stay in the report, so choose neutral origin and category names. Set
`ATTEST_BENCH_ID_KEY` to a random, high-entropy secret kept outside the report (for example the
output of `openssl rand -hex 32`) to key the id hash with HMAC-SHA256, and use the same key
across runs so their rows still match. Without the key, anyone who can guess a case id can
confirm it by hashing it. The runner warns when a private run has no key, and when the key is
shorter than 32 characters or has fewer than 8 distinct characters. Reports record a
fingerprint of the key, never the key itself, and `compare.py` refuses to compare reports whose
ids were hashed with different keys.

The withholding covers the report only. The provider still sees each case while grading it,
and the response cache quotes the cases, so keep both the case files and the cache private.

## Labelling

Labels come from people, never from attest. Each case is labelled from the recorded run alone,
against the
[labelling guidelines](https://github.com/peace-orefejo/attest/blob/main/benchmarks/annotations/guidelines.md)
(themselves a draft), before anyone looks at attest's output.

A case is confirmed through blind double labelling with `benchmarks/runners/annotate.py`:

1. **`template`** writes blank label files for one annotator. Each file is tied to the exact run
   it labels, so if the run is edited later the file is reported as stale.
2. Each annotator fills in their own files without opening the case files, anyone else's labels
   or attest's output. The tool doesn't enforce this; it's a procedure reviewers check.
   **`serve`** opens a local page for this, one case at a time, instead of editing JSON
   (see below).
3. **`agreement`** reports, per check, the share of identical labels and Cohen's kappa between
   two annotators, and lists every disagreement. Kappa below 0.6 on a check means the
   guidelines are unclear for it.
4. **`settle`** records how one disagreement was settled, by discussion between the case's
   annotators or by an owner ruling recorded in the guidelines' rulings log, in an append-only
   adjudication log. `settle --replace` corrects an entry by appending one that supersedes it.
   A settlement goes stale if the run or the annotators' labels change.
5. **`merge`** lists which cases can be confirmed and why the rest can't; `merge --write`
   writes the agreed labels into the case files and marks them `confirmed`. A case marked
   ambiguous is never confirmed.

A disagreement is never settled by checking what attest said.

### Labelling in your browser

```bash
# public datasets
uv run python benchmarks/runners/annotate.py serve po

# a private dataset (such as the Vera cases), with its labels outside the repository
uv run python benchmarks/runners/annotate.py --datasets ~/vera-cases \
    --labels ~/vera-labels serve po
```

This opens a browser tab where you label your own blank label files one case at a time: the run
on one side, the form for its check on the other, the guidelines a click away and keyboard
shortcuts for every label. If you have no label files yet it offers to create them, as
`template` does. It saves in the same file format, so partial work stays unfinished and
`agreement` and `merge` read the files as before. It only shows your own folder, never other
annotators' labels, the cases' draft labels or notes, or attest's output, and it never leaves
your machine: it listens on 127.0.0.1 only, needs the random token in the link it prints, and
loads nothing from the internet.

## Running it

```bash
# no key: tool use without the answer question, and the injection scan
uv run python benchmarks/runners/run.py --offline

# faithfulness on dev, with a key
uv run python benchmarks/runners/run.py --check faithfulness --split dev \
    --provider anthropic --cache-dir .cache/bench --out benchmarks/reports/faith-dev.json
```

An offline run exercises the pipeline but doesn't measure attest: faithfulness and role
adherence are skipped, unrecovered tool errors come back unchecked, and injection is scan-only.

Each run writes a JSON report and prints a Markdown summary. A report is publishable only when
every selected check has cases in the split and at least 95% coverage (`--min-coverage`), no
case carries a draft label, the budget didn't run out and the run wasn't offline. Otherwise the
summary opens with **NOT PUBLISHABLE** and the reasons. While every label is a draft, every
report is marked this way.

To compare two reports:

```bash
uv run python benchmarks/runners/compare.py benchmarks/reports/old.json benchmarks/reports/new.json
```

`compare.py` refuses (exit 2) when the reports aren't like for like: different dataset
versions, splits, settings, provider or model (unless `--allow-model-change`), cases that
errored or didn't run, or a check below the coverage threshold. Otherwise it prints the deltas
per check and per origin, lists each case whose result flipped, and exits 1 when F1 or recall in
any binary view drops by more than the tolerance (0.02 by default). The same rule applies to
each origin with at least 10 cases in both reports, so a drop in one source can't hide behind a
gain in another.

## Hugging Face export

`benchmarks/runners/export_hf.py` exports the public cases as a Hugging Face dataset: one config
per check with its `dev`, `validation` and `heldout` splits, a generated dataset card (with the
draft-label status, counts, provenance, licences and citations), the licence files, and a
`manifest.json` recording the `dataset_version`.

```bash
uv run python benchmarks/runners/export_hf.py build      # writes benchmarks/hf-build/
uv sync --group hf                                       # installs huggingface_hub
uv run --group hf python benchmarks/runners/export_hf.py upload --repo pandorasBoxee/attest-benchmark
```

The intended home for the dataset is `pandorasBoxee/attest-benchmark` on the Hugging Face Hub;
it may not have been uploaded yet. An upload tags the revision
`dv-<first 12 characters of dataset_version>`, so a published report can be matched to the
exact data it ran on, and it refuses a missing or out-of-date build. Private datasets are never
exported. Once uploaded, the held-out labels are public, so a held-out score only means
something for a system that wasn't tuned on them.
