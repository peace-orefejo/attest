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
| `--allow-pr-attestignore` | off | Use pattern files even when the pull request changes them. Without it, that is refused. See [In CI](#in-ci-read-patterns-from-the-base-branch). |

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
itself. `Attest(exclude=...)` takes a list of patterns, a `Path` to one pattern file, or the
result of `load_exclusions`. A bare string raises `TypeError`, because `"team.attestignore"`
could mean a pattern or a file: write `["*.env"]` or `Path("team.attestignore")`.

**Pattern syntax** is the gitignore subset below.

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
One difference from git: a pattern with an unclosed character class, such as `a[b`, matches the
literal name `a[b` in attest and nothing in git.

**How paths are matched.** Paths reach attest in many forms (diff keys, a reviewer's read
arguments, grep output, artifact paths), so matching fails closed, leaning towards leaving a
file out:

- A path is normalized first: `\` counts as `/`, `//` and `./` are collapsed, and `..` is
  resolved, so `src/../secrets/k.env` is `secrets/k.env`.
- An absolute path (`/home/me/repo/fixtures/users.json`, `C:\repo\...`), or one that climbs
  above its start with `..`, is matched from every one of its segments, since attest can't know
  where your repository starts. So `fixtures/**` and `/fixtures/` both match
  `/home/me/repo/fixtures/users.json`. This can over-match: `/build/` also matches
  `/home/me/build/repo/app.py`. In `attest run`, an artifact path inside the current directory
  is matched relative to it instead.
- A path also counts as excluded when its case-folded, NFC-normalized form matches the
  case-folded patterns, with trailing spaces and dots trimmed from each segment. macOS and
  Windows treat `Secrets/k.env`, `secrets/k.env` and a decomposed `café.env` as the same file,
  so attest does too, on every platform. A `!` pattern re-includes a file only if both forms
  agree.
- A path over 4,096 characters or 1,024 segments is always excluded.

**What an exclusion covers.** In [code review](code-review/index.md#leaving-files-out), excluded
files' diffs and reads are replaced by a one-line note everywhere: in the grading evidence,
attest's own reviewer, the guideline check and the injection scan. A read is hidden when any of
its path-like arguments (`path`, `file_path`, a `paths` list, any string but the search text)
names an excluded file or directory. A grep whose output names an excluded file anywhere (a
`path:line:` prefix, a ripgrep heading line, a NUL-separated name, absolute or relative) is
withheld whole, since its other lines may belong to that file. A grep too long to check
(50,000 path segments' worth of candidate names) keeps only the lines checked so far. In
`attest run`, an artifact whose `path` or `name` matches is replaced by a one-line note before
any check runs: it is never read, scanned or sent to a model, and its location is listed in
`metadata["artifacts_excluded"]`. Its `path` is matched as written and with symlinks resolved,
so a link to an excluded file is excluded too. Tool outputs are not files, so patterns never
apply to them.

Exclusions cover file contents only. They don't apply to the text of a review output or an
answer, which is checked as written, nor to file paths, which still appear in notes, the
changed-file list and the result.

Exclusions only remove evidence. A `!` pattern re-includes only what another of your patterns
excluded; it can't bring back a generated file or lockfile attest leaves out by itself.

### In CI: read patterns from the base branch

A pull request that edits `.attestignore` could hide its own changes from the review. So
`attest review` refuses with `invalid_input` (exit 2) when the pull request's diffs or
changed-file list touch `.attestignore` or any `--exclude-file` it read, matched against the
current directory and every directory above it. Read the patterns from the base branch instead:

```bash
git show origin/main:.attestignore > "$RUNNER_TEMP/base.attestignore"
attest review review.json --no-attestignore --exclude-file "$RUNNER_TEMP/base.attestignore"
```

Pass `--allow-pr-attestignore` to use the pull request's own patterns anyway, for example when
you trust its author. In Python, `review()` doesn't refuse; it adds a warning when the pull
request changes a file named like one the patterns came from.
