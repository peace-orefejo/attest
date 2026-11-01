# Converters

Each converter turns a small, vendored subset of a public agent-run dataset into benchmark
cases. One file per origin:

- `<origin>.py` regenerates that origin's case files from its inputs, deterministically:
  `uv run python benchmarks/converters/<origin>.py`. `<origin>_test.py` sits beside it.
- Inputs live under `../sources/<origin>/`: only the files used, the upstream `LICENSE`
  verbatim, a `NOTICE` line crediting it, and `SOURCE.md` (upstream URL, exact commit, each
  vendored file's upstream path and sha256, what was selected and why, what was stripped).
- Output goes to `../datasets/<check>/<split>-<origin>.jsonl`, and only that origin's converter
  writes those files. Every case has `origin: "<origin>"`, `source: "community"`, an id
  prefixed with the origin, a `task_family` that keeps related runs in one split, and an
  `origin_ref` pointing at the upstream run.
- Strip anything that could act as a label (rewards, success or security flags, grader output),
  and drop or redact any real person's personal data.
- Labels are drafts by the converter author, following
  [the guidelines](../annotations/guidelines.md): `label_status: "draft"`, `annotators: []`,
  `notes` starting with `DRAFT label by the converter author;`. Never label from attest's
  output.

The loader (`../runners/bench_load.py`) checks every file's origin, the split rules and the
`task_family` leak rule. See [the benchmark README](../README.md#external-origins).
