---
title: "Command line reference"
description: "The attest command line for AI agent evaluation: run, tools, injection, role, review, demo, stats, models and schema, with every option."
---

# Command line

Run commands take a `.json` file with one run, or a `.jsonl` file with one run per line. Every
command prints [JSON](json-output.md). Commands that use a model accept `--provider` (`-p`) and
`--model` (`-m`).

| Command | Does | Needs a key? |
|---|---|---|
| `attest run FILE` | Grades every run in FILE with the chosen checks. | Yes |
| `attest tools FILE` | Tool-use check. `--appropriate` adds a model check of each tool choice; `--check-answer` asks a model whether the final answer reports unrecovered tool errors. | Only with `--appropriate` or `--check-answer` |
| `attest injection FILE` | Prompt-injection scan. `--deep` checks whether the agent obeyed. | Only with `--deep` |
| `attest role FILE` | Role-adherence check. | Yes |
| `attest review FILE` | Checks an AI code reviewer's outputs. | Yes |
| `attest demo [FILE]` | A plain LLM judge and attest side by side. FILE defaults to `examples/trajectory.json`. | Yes |
| `attest stats PASSED N` | A pass rate with a 95% confidence interval. | No |
| `attest models PROVIDER` | A provider's models: fetched live when its key is set (`source: live`), a curated list otherwise. | No |
| `attest schema [COMMAND]` | The JSON Schema of a command's output; `error` for the error envelope, nothing for all. | No |

## `attest run`

```bash
attest run runs.jsonl --checks faithfulness,tool_use,injection,role > report.json
```

| Option | Default | Meaning |
|---|---|---|
| `--checks` | `faithfulness,tool_use` | Any of `faithfulness`, `tool_use`, `injection`, `role`. |
| `--kind` | `factual` | Answer kind: `factual`, `plan`, `code` or `auto`. |
| `--appropriate` | off | Add the model tool-choice check. |
| `--max-claims N` | `40` | Check at most N claims per answer. Claims past the cap aren't checked, so the run goes to review. Must be 0 or more. |
| `--max-calls`, `--max-tokens` | none | Stop before going over this budget (exit code 3). |
| `--cache-dir PATH` | none | Reuse grading verdicts across runs. |
| `--exclude PATTERN`, `--exclude-file PATH`, `--no-attestignore` | `.attestignore` if present | Leave out artifacts whose path or name matches. See [Excluding files](#excluding-files). |

Injection inside `attest run` is always deep (it checks whether the agent obeyed a payload), so
it makes model calls. Use `attest injection` for a scan without a key.

## `attest injection`

| Option | Meaning |
|---|---|
| `--deep` | Check with a model whether the agent obeyed each payload. |
| `--patterns FILE` | Add regex patterns from a JSON file. |
| `--patterns-only` | Use only `--patterns`, not the built-in detectors. Needs `--patterns`. |
| `--no-extract-files` | Don't extract embedded files before scanning. |
| `--allow-paths` | Read local files the run refers to by path. |

## `attest review`

```bash
attest review review.json -g REVIEW.md --mode issue=strict
```

The file holds a [`PullRequest`](code-review/outputs.md#pullrequest) and its
[`ReviewOutput`](code-review/outputs.md#reviewoutput)s. Leave out `outputs` and attest
[writes the review](code-review/writing.md) first.

```json
{
  "pr": {"diffs": {"billing/cart.py": "--- a/billing/cart.py\n+++ b/billing/cart.py\n@@ ..."}},
  "outputs": [{"output_type": "issue", "text": "cart_total no longer checks for a missing user."}]
}
```

| Option | Default | Meaning |
|---|---|---|
| `-g`, `--guidelines PATH` | none | A file of [review rules](code-review/guidelines.md). Repeatable. |
| `--follow` / `--no-follow` | on | Drop outputs that break a review rule. |
| `--mode TYPE=MODE` | per type | Override a [gate mode](code-review/index.md#keep-or-drop-the-gate), e.g. `issue=strict`. Repeatable. |
| `--deep` / `--no-deep` | on | Confirm injection hits with the grading model and check which outputs obeyed them. |
| `--max-claims N` | `40` | Check at most N claims per output. An output with more is [dropped](code-review/outputs.md#what-drops-an-output). Must be 0 or more. |
| `--exclude PATTERN` | none | Leave out files matching this pattern. Repeatable. See [Excluding files](#excluding-files). |
| `--exclude-file PATH` | none | Read exclusion patterns from this file. Repeatable. |
| `--attestignore` / `--no-attestignore` | on | Read `.attestignore` from the current directory when it exists. |

## Excluding files

Tell attest which files to leave out, to save cost, cut noise, or keep secrets, fixtures and
large data files away from the grading model. `attest run` and `attest review` take the same
three options, and the Python API takes the same patterns as `Attest(exclude=[...])`.

```text
# .attestignore
# Secrets never leave this machine.
secrets/
*.pem
.env*

# Big or noisy files.
fixtures/**
data/*.parquet

# But keep this one.
!fixtures/schema.json
```

```bash
attest review review.json --exclude "*.snap" --exclude-file team.attestignore
attest run runs.jsonl --no-attestignore --exclude "uploads/"
```

**Where patterns come from**, in this order:

1. `.attestignore` in the current directory, when it exists (turn this off with
   `--no-attestignore`).
2. Each `--exclude-file`, in the order given.
3. Each `--exclude`, in the order given.

The last pattern that matches a path decides, so a later `!pattern` re-includes a file an earlier
pattern excluded. A pattern file that can't be read, isn't UTF-8 or is over 1 MB, and more than
1,000 patterns in all, are `invalid_input` errors (exit 2); attest never skips them silently.
In Python, `load_exclusions(patterns, files=[...], discover=True)` reads files the same way and
raises `ExclusionError` (a `ValueError`); `Attest(exclude=...)` never reads `.attestignore` by
itself.

**Pattern syntax** is the gitignore subset below. Matching is case-sensitive and uses `/` in
paths.

| Pattern | Matches |
|---|---|
| `# text` | Nothing: a comment. Blank lines are skipped too. Trailing spaces are dropped. |
| `*.pem` | A name with no `/` matches at any depth, as a file or a directory. |
| `/build.log`, `docs/private.md` | A `/` at the start or in the middle anchors the pattern to the root. |
| `*`, `?`, `[a-z]`, `[!0-9]` | Any run of characters except `/`, one such character, a character class or its negation (`[^0-9]` works too). |
| `**/fixtures`, `data/**`, `a/**/b` | `**` between slashes matches any number of directories, including none. `data/**` matches everything inside `data`. |
| `secrets/` | A trailing `/` matches directories only, and so everything inside them. |
| `!fixtures/schema.json` | Re-includes a path an earlier pattern excluded. |
| `\#name`, `\!name`, `\*` | A backslash makes the next character literal. |

As in git, a file inside an excluded directory can't be re-included: after `secrets/`,
`!secrets/public.txt` has no effect. Write `secrets/*` and then `!secrets/public.txt` instead.

**What an exclusion covers.** In [code review](code-review/index.md#leaving-files-out), excluded
files' diffs, file reads and grep lines are replaced by a one-line note everywhere: in the
grading evidence, attest's own reviewer, the guideline check and the injection scan. In
`attest run`, an artifact whose `path` or `name` matches is replaced by a one-line note before
any check runs: it is never read, scanned or sent to a model, and its location is listed in
`metadata["artifacts_excluded"]`. A `path` is matched as written and, when it is absolute and
inside the current directory, relative to it. Tool outputs are not files, so patterns never
apply to them, and nor do they apply to an output's or answer's own text.

Exclusions only remove evidence. A `!` pattern re-includes only what another of your patterns
excluded; it can't bring back a generated file or lockfile attest leaves out by itself.

In CI, read exclusion files from the base branch: a pull request that edits `.attestignore` could
otherwise hide its own changes from the review. `attest review` warns when the pull request
changes a file the patterns came from.
