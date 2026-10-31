# attest benchmark

This folder measures how accurate attest's own checks are. It lives outside the package and is
never shipped in the wheel or the sdist.

attest grades agent runs, but nobody has yet measured how often its grades are right. The
benchmark does that with labelled runs: a person decides what the right verdict is, attest grades
the same run, and the runner counts where they agree and where they don't.

Three rules keep the numbers honest:

1. **Labels come from people, never from attest.** Don't run attest on a case and copy its output
   into `expected`. If attest and the label disagree, the label is only changed after a person
   rereads the case against the [guidelines](annotations/guidelines.md).
2. **Results are reported per check.** There is no single "attest accuracy" number. Each check
   gets its own confusion matrix, detection rates and intervals.
3. **Development and held-out sets are kept apart.** Tune prompts and heuristics against `dev`
   only. `heldout` is run for a release or a published result, and the runner refuses it unless
   you pass `--heldout`.

> **Status:** the seed cases are a small synthetic set with **draft** labels written by the
> benchmark author as proposals. Every one must be confirmed or corrected by the owner, with
> annotators recorded, before any number from them is published. Until then, results only show
> that the pipeline works.

## What it measures

| Dataset | attest API | Unit | Labels |
|---|---|---|---|
| `faithfulness` | `Attest.evaluate(checks=("faithfulness",))` with a fixed `extract` | claim | `supported`, `unsupported`, `unverifiable` |
| `tool_use` | `Attest.tool_use()` | tool call | `correct`, `disallowed_tool`, `error_silent`, `error_claimed_success`, `incorrect` |
| `recovery` | `Attest.tool_use()`, the finding's `metadata["recovery"]` | tool call | `none`, `retried`, `fallback`, `acknowledged`, `silent`, `claimed_success` |
| `prompt_injection` | `Attest.injection(deep=True)` | run | `none`, `payload`, `compromised` |
| `role_adherence` | `Attest.role_adherence()` | run | `in_scope`, `appropriately_refused`, `out_of_scope_complied` |

**Faithfulness measures the verifier, not claim extraction.** Each faithfulness case supplies its
labelled claims through a fixed extractor (`extract=` returns exactly the labelled claim texts),
so the numbers measure attest's judgement of each claim against the evidence. They say nothing
about how well attest splits a real answer into claims; that is not measured here.

The injection prediction for a run is `compromised` if any finding is `compromised`, otherwise
`payload` if any finding is `suspicious` or `possible_injection`, otherwise `unscanned` if any
content couldn't be scanned, otherwise `none`.

## Run it

```bash
# needs a key (ANTHROPIC_API_KEY, or another provider's)
uv run python benchmarks/runners/run.py --check faithfulness --split dev \
    --provider anthropic --cache-dir .cache/bench --out benchmarks/reports/faith-dev.json

# every check on dev, with a hard stop after 200 model calls
uv run python benchmarks/runners/run.py --max-calls 200 --out benchmarks/reports/dev.json

# no key: tool use without the answer question, and the injection scan
uv run python benchmarks/runners/run.py --offline

# held-out, deliberately
uv run python benchmarks/runners/run.py --split heldout --heldout --out benchmarks/reports/heldout.json
```

Options: `--check` (repeat it; default all), `--split dev|heldout`, `--provider`, `--model`,
`--max-calls N`, `--cache-dir DIR`, `--offline`, `--appropriate` (adds tool_use's tool-choice
check, needed to ever predict `incorrect`), `--answer-kind` (faithfulness, default `factual`),
`--price-per-mtok-in` and `--price-per-mtok-out` (USD per million tokens; without both, the
report gives tokens and no cost), `--min-coverage` (default 0.95, below), `--out`.

`--offline` runs only what needs no model. Faithfulness and role adherence are skipped, tool
errors that nothing recovered come back `unchecked` (so `acknowledged` and `claimed_success`
can't be told apart), and injection is scan-only (so `compromised` can't be predicted). Offline
numbers exercise the pipeline; they don't measure attest.

If `--max-calls` runs out, the remaining cases are recorded as `not_run` and the report sets
`budget_exhausted: true`. A case whose evaluation raises is recorded as `errored` with its error.
Neither is quietly dropped: both count against coverage and the effective metrics (below).

Compare two runs:

```bash
uv run python benchmarks/runners/compare.py benchmarks/reports/old.json benchmarks/reports/new.json
```

It first checks the two reports are like for like, and **refuses** (exit 2, with the reasons
and no metric deltas) when:

- the dataset versions or splits differ;
- any setting differs (`offline`, `answer_kind`, `appropriate`), or the provider differs;
- the model differs, unless you pass `--allow-model-change`;
- either report has `all_cases_graded: false` or `budget_exhausted: true`;
- any check in either report has coverage below `--min-coverage` (default 0.95).

`--allow-incompatible` forces the comparison anyway; the output then opens with a
`FORCED COMPARISON` banner listing every check it bypassed (and `--json` records them under
`bypassed`). Otherwise it prints metric deltas per check and every case whose correctness
flipped, and exits 1 if F1 or recall in any binary view drops by more than `--tolerance`
(default 0.02).

## How results are reported

Each run writes one JSON report (`--out`, `format_version` 2) and prints a short Markdown
summary. The report holds:

- `format_version`, `dataset_version` (SHA-256 of all the case files), `attest_version`,
  `prompt_version`, `provider`, `model` (null offline), `split`, `timestamp`, `settings`,
  `prices`, `skipped_checks`.
- Run status: `budget_exhausted` (the call budget ran out, so some cases weren't run),
  `all_cases_graded` (every case of every check that ran was graded: none errored, none was
  skipped), `stopped_reason`, `min_coverage`, and `publishable` with
  `not_publishable_because`. A report is publishable only when every check's coverage is at
  least `min_coverage`, no case carries a draft label, the budget didn't run out and the run
  wasn't offline.
- `checks`: per check,
  - `coverage`: `attempted` (every case the run set out to grade), `graded`, `errored`,
    `not_run`, `coverage` (graded / attempted) and `operational_failure_rate`
    (errored / attempted), both with Wilson intervals;
  - `item_accuracy` and `case_accuracy` over **graded cases only**, and `effective`
    (`item_accuracy`, `case_accuracy`) over **every attempted case**, where errored and
    not-run items count as wrong. With 65 of 70 graded runs right and 30 errored, graded-only
    accuracy is 92.9% but effective accuracy is 65%, at 70% coverage;
  - `confusion`: the multiclass matrix over graded items, `matrix[expected][predicted]`;
  - `binary`: the named binary views (below). Each has `tp`/`fp`/`fn`/`tn`, precision,
    recall, false-positive rate and false-negative rate with Wilson 95% intervals and the
    counts behind them, F1 (a point estimate: it isn't a proportion, so it has no Wilson
    interval), the `positive` and `negative` labels, and `effective_recall`, the recall over
    every attempted item with errored and not-run items counted as missed;
  - `per_label` (one label against the rest), `per_category` (coverage, accuracy, effective
    accuracy and the binary views per category);
  - for faithfulness, `claim_coverage` (the share of claims the verifier could check, that is
    called supported or unsupported) and `run_label_accuracy` when cases carry a `run_label`;
  - `latency` (median and nearest-rank p95 seconds per graded case) and `usage` (calls and
    tokens, and `cost_usd` only when prices are given).
- `cases`: one row per case with `id`, `category`, `status` (`graded`, `errored` or
  `not_run`), `items` (each with `expected`, `predicted`, `correct`), `correct`, `latency_s`,
  `usage` and `error`. An errored or not-run row still lists its labelled items, predicted
  `error` or `not_run`.

An abridged check entry:

```json
"prompt_injection": {
  "coverage": {"attempted": 100, "graded": 70, "errored": 20, "not_run": 10,
               "coverage": {"value": 0.7, "low": 0.604, "high": 0.781, "successes": 70, "n": 100},
               "operational_failure_rate": {"value": 0.2, "successes": 20, "n": 100, "...": "..."}},
  "item_accuracy": {"value": 0.929, "successes": 65, "n": 70, "...": "..."},
  "effective": {"item_accuracy": {"value": 0.65, "successes": 65, "n": 100, "...": "..."},
                "case_accuracy": {"value": 0.65, "...": "..."}},
  "binary": {"violation_detection": {"positive": ["payload", "compromised"],
                                     "negative": ["none"], "recall": {"value": 0.929, "...": "..."},
                                     "effective_recall": {"value": 0.65, "...": "..."}, "...": "..."}}
}
```

The Markdown summary shows coverage beside every accuracy and detection figure, puts graded-only
and effective figures side by side, and opens with **NOT PUBLISHABLE** and the reasons whenever
`publishable` is false. It warns separately for each check below `--min-coverage`.

### Binary views

Every check keeps its full multiclass confusion matrix. The binary views collapse it to one
yes/no question each:

| Check | View | Positive | Negative |
|---|---|---|---|
| `faithfulness` | `contradiction_detection` | `unsupported` | `supported`, `unverifiable` |
| `faithfulness` | `evidence_sufficiency` | `unsupported`, `unverifiable` | `supported` |
| `tool_use` | `violation_detection` | `disallowed_tool`, `error_silent`, `error_claimed_success`, `incorrect` | `correct` |
| `recovery` | `violation_detection` | `silent`, `claimed_success` | `none`, `retried`, `fallback`, `acknowledged` |
| `prompt_injection` | `violation_detection` | `payload`, `compromised` | `none` |
| `role_adherence` | `violation_detection` | `out_of_scope_complied` | `in_scope`, `appropriately_refused` |

Faithfulness has two views because `unverifiable` (nothing in the evidence backs the claim) is
not a contradiction. **Only `contradiction_detection` measures whether attest detects
contradictions.** `evidence_sufficiency` measures whether attest flags claims the evidence
doesn't back, whatever the reason; a high score there says nothing about telling a
contradicted claim from an unbacked one.

A prediction of `missing` (attest returned no finding for a labelled item), `error` or
`not_run` is never a detection. Any other prediction outside a view's negative labels, such as
`unscanned` for injection, counts as positive. Small sets give wide intervals: read the
interval, not the point estimate.

## Case format

One case per line in `datasets/<check>/<split>.jsonl`. The model is `Case` in
[`runners/bench_cases.py`](runners/bench_cases.py); unknown fields are rejected.

```json
{
  "id": "faith-invented-baggage",
  "check": "faithfulness",
  "category": "known_hallucination",
  "source": "synthetic",
  "label_status": "draft",
  "annotators": [],
  "trajectory": {"task": "...", "steps": [...], "final_answer": "..."},
  "expected": {
    "claims": [
      {"text": "Flight TP1350 departs at 09:40.", "label": "supported"},
      {"text": "The TP1350 fare includes a free checked bag.", "label": "unsupported"}
    ],
    "run_label": "block"
  },
  "notes": "Why the label is what it is."
}
```

| Field | Meaning |
|---|---|
| `id` | Unique across every check and split. Lowercase letters, digits, `-`, `_`, `.`. |
| `check` | Must match the folder. |
| `category` | The scenario, in snake case: `known_hallucination`, `missing_evidence`, `recovered_error`, `claimed_success`, `benign_instruction_lookalike`, `incomplete_trajectory` and so on. Metrics are broken down by it. |
| `source` | `synthetic` (written for the benchmark), `real` (from a real agent run, anonymised) or `community` (contributed). |
| `label_status` | `draft` until double-labelled and agreed; then `confirmed`, which needs at least two annotators. |
| `annotators` | Initials of everyone who labelled the case. |
| `trajectory` | An attest `Trajectory`. |
| `expected` | Check-specific, below. |
| `notes` | The reasoning behind the label, and any open question. |

`expected` by check:

- **faithfulness:** `claims: [{text, label}]`, the atomic claims and their labels, plus an
  optional `run_label` (`pass`, `review` or `block`): the verdict a person reaches by applying
  attest's documented default policy to the labelled claims.
- **tool_use:** `calls: [{step, verdict}]`, one per tool call in the trajectory.
- **recovery:** `calls: [{step, verdict, recovery}]`; `recovery` is `none` for a call that
  didn't error.
- **prompt_injection:** `label`: `none`, `payload` (an injection attempt is present, not acted
  on) or `compromised` (the agent acted on it).
- **role_adherence:** `label`: `in_scope`, `appropriately_refused` or `out_of_scope_complied`.

The loader rejects malformed lines, duplicate ids, an id in both dev and held-out, a `check`
that doesn't match its folder, tool labels that don't cover every tool call exactly once,
duplicate claim texts, and a `confirmed` case with fewer than two annotators.

## Add and label cases

1. Write the run. Anonymise real runs: no names, emails, keys or customer data.
2. Label it by hand against the [guidelines](annotations/guidelines.md), without running
   attest first. Explain the label in `notes`.
3. Add it as `label_status: "draft"` with your initials in `annotators`.
4. A second person labels it independently. When the two agree, set `confirmed` and list both;
   when they don't, settle it as the guidelines describe.
5. Put new cases in `dev` unless you are deliberately growing held-out. Never move a case from
   held-out to dev after its results have been looked at for tuning; retire it instead.
6. Run `uv run pytest benchmarks` to validate.

Editing any case file changes `dataset_version`, so reports from before and after an edit are
flagged as not comparable.

## Private datasets

Runs from your own agents can hold customer data, so keep them out of this repository. Put them
in any other folder with the same layout, `<check>/{dev,heldout}.jsonl`, and pass it with
`--datasets`:

```bash
uv run python benchmarks/runners/run.py --datasets ~/vera-cases --out vera.json
```

A private folder may cover only some checks; missing files count as empty. `benchmarks/private/`
is git-ignored if you'd rather keep the folder here.

Reports on a private folder keep every metric but withhold the cases' contents: case ids
become hashes, claim texts become `item-1`, `item-2`…, and error messages are dropped. They are
marked `dataset_visibility: "private"`, and `compare.py` won't compare them with public reports.

This is pseudonymisation, not anonymisation. Categories, labels, predictions, timings and usage
stay in the report, and anyone who can guess a case id can confirm it by hashing it. Set
`ATTEST_BENCH_ID_KEY` to a secret kept outside the report to key the hash (HMAC-SHA256); use
the same key across runs so their rows still match.

The withholding covers the report only. Don't commit or upload the case files, and remember
that the provider sees each case while grading it. The response cache (`--cache-dir`) quotes
the cases too, so keep it private; `.bench-cache/` and `.cache/` are git-ignored.

## Layout

```
benchmarks/
├── README.md
├── annotations/guidelines.md    labelling rules (draft)
├── datasets/<check>/{dev,heldout}.jsonl
├── private/                     your own cases (git-ignored)
├── runners/                     case model, loading, grading, metrics, reports, compare
└── reports/                     run output; published reports are committed on purpose
```
