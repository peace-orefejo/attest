---
title: "Code review mode: check AI code review comments"
description: "Check AI code reviewer outputs against the diff: keep real issues, drop false ones and wrong summaries before people see them."
---

# Code review mode

AI code reviewers flag false issues and write summaries that don't match the diff. Code review
mode checks each reviewer output against the code it describes, then decides whether to keep it.

![Code review mode](../assets/diagrams/code-review-flow.svg){ .diagram }

Put it between your review pipeline and the people who read the results. If you don't have a
reviewer, attest can [write the review itself](writing.md) and check that too.

## The four output types

| Type | What it is | Example | Default gate mode |
|---|---|---|---|
| `issue` | A problem the reviewer flagged. | "`cart_total` reads past the end of `items`." | lenient |
| `diff_summary` | A summary of one file's changes. | "Adds retry with exponential backoff to `fetch_user`." | strict |
| `group_summary` | A summary of several related files, or the whole pull request. | "Moves session checks into middleware across 3 files." | strict |
| `canvas_answer` | An answer to a question someone asked about the change. | Q: "Does this change the public API?" A: "No, only private helpers changed." | strict |

## Keep or drop: the gate

After an output is graded, the **gate** decides whether to keep it (show it to people) or drop
it. The gate mode only changes how faithfulness problems count:

- **lenient** drops the output when the code contradicts it (`unsupported`).
- **strict** also drops it when the code shown doesn't back it up (`unverifiable`).

Issues default to lenient because a real bug often depends on code the reviewer didn't include.
Summaries and answers describe the change itself, so a claim the diff doesn't show is a problem.

In both modes, an output is also dropped if it breaks one of your
[review rules](guidelines.md) or obeyed text planted in the pull request
([injection](injection.md)). [What drops an output](outputs.md#what-drops-an-output) has the
full table.

## End to end

```python
from attest import Attest
from attest.code_review import PullRequest, ReviewOutput

pr = PullRequest(diffs={"billing/cart.py": diff}, changed_files=["billing/cart.py"])
outputs = [
    ReviewOutput(output_type="issue", text="cart_total no longer checks for a missing user, ..."),
    ReviewOutput(output_type="issue", text="The loop in cart_total uses range(len(items) + 1) ..."),
]

result = Attest().review(pr, outputs, guidelines="REVIEW.md")

post = result.filter(outputs)      # the outputs to show, in their original order
payload = result.model_dump_json() # or store the decisions
```

`review()` scans the pull request for planted instructions once, grades each output against its
evidence, checks it against your [review guidelines](guidelines.md), and gates it. Outputs that
carry no diffs or changed-file list of their own use the pull request's.

The result has one decision per output, saying whether to keep it and why, plus `kept` and
`dropped` lists of indexes. [Outputs and decisions](outputs.md) lists every field. From the
shell, `attest review` prints the same result as JSON (see
[Command line](../cli.md#attest-review)). The full script is `examples/code_review_gate.py`.

Options:

| Argument | Default | Meaning |
|---|---|---|
| `outputs` | `None` | The reviewer's outputs. Leave it out and attest [writes the review](writing.md). |
| `guidelines` | `None` | Your [review rules](guidelines.md): a markdown file, markdown text, or a list of files. Without them, outputs are checked for faithfulness only. |
| `follow_guidelines` | `True` | Check outputs against your rules and drop the ones that break one. Has no effect without `guidelines`. |
| `modes` | `None` | Override the gate mode per output type, e.g. `{"issue": "strict"}`. |
| `deep` | `True` | Confirm injection hits with the grading model and check which outputs obeyed them. |
| `limits` | `None` | An `EvidenceLimits` budget for large diffs. |
| `answer_kind` | `"code"` | The answer kind used to grade each output. |
| `max_claims` | `40` | The most claims checked per output. An output with more is dropped, since the rest were never checked. |
| `exclude` | `None` | Gitignore-style patterns for files to [leave out](#leaving-files-out). Set on `Attest(exclude=[...])`, or pass `exclude=` to `attest.code_review.review()`. |

For a custom pipeline, the steps are public too:

- `to_run(output)` turns one output into a run whose tool outputs are its diffs and file reads.
  Pass `exclude=[...]` to replace excluded files with notes.
- `check_code_injection(pr, outputs)` scans the pull request (see [Injection in diffs](injection.md)).
- `gate(report, output_type, injection=..., paths=..., output_index=...)` decides one output.

## How code is graded

Each output is graded like any other answer: attest turns it into a run whose evidence is the
diffs (and any files the reviewer read), then checks each claim with the `code`
[answer kind](../concepts.md#answer-kinds). That standard reads evidence the way a reviewer
should:

- Lines starting with `+` were added, lines starting with `-` were removed and are gone, and
  unmarked lines are unchanged context.
- The language's standard semantics count as evidence. `range(len(xs))` yields only valid
  indices, and 900 seconds is 15 minutes.
- The pull request's list of changed files is complete. A claim that some other file changed is
  unsupported.
- The code wins over comments, docstrings and commit messages. A comment can't make a claim true.
- Recommendations and speculation about intent are dropped before grading.
- Your [review rules](guidelines.md) are part of the evidence. They settle what the team
  requires, never what the code does.

## Large changes

Each output's evidence is kept within a budget (12,000 characters per file and 60,000 per run by
default; pass `limits=EvidenceLimits(...)` to change it). Lockfiles are reduced to their version
changes, generated files to a line count, and large diffs keep whole hunks until the budget runs
out. The changed-file list is never cut. Each decision's `omissions` says what was left out.

## Leaving files out

Tell attest which files to leave out of the review, for cost, noise or privacy: secrets,
fixtures, snapshots, large data files. Patterns use gitignore syntax; the
[command line page](../cli.md#excluding-files) has the full syntax, where patterns come from,
and the limits.

```python
from pathlib import Path

from attest import Attest, load_exclusions

judge = Attest(exclude=["secrets/", "*.pem", "fixtures/**", "!fixtures/schema.json"])
result = judge.review(pr, outputs)
result.excluded_files              # ["secrets/prod.env", ...]: left out, not reviewed

# or read .attestignore from the current directory, plus a team file
judge = Attest(exclude=load_exclusions(files=["team.attestignore"], discover=True))

# or one pattern file (a bare string is refused: is it a pattern or a file?)
judge = Attest(exclude=Path("team.attestignore"))
```

```text
# .attestignore
secrets/
*.pem
fixtures/**
!fixtures/schema.json
```

From the shell, `attest review` reads `.attestignore` from the current directory and takes
`--exclude PATTERN` and `--exclude-file PATH`. It refuses (exit 2) when the pull request
changes one of those pattern files, unless you pass `--allow-pr-attestignore`; in CI, read the
patterns from the base branch (see [the command line page](../cli.md#in-ci-read-patterns-from-the-base-branch)).

An excluded file's contents never reach a model or the injection scan. Each excluded diff or
file read is replaced by one line, such as
`secrets/prod.env: excluded by the user's exclusion rules`, in the grading evidence, in
attest's own reviewer when it [writes the review](writing.md), and in the guideline check. The
changed-file list keeps every path, marking excluded ones, so it stays complete.

Matching fails closed, because paths arrive in many forms. A path is normalized (`\`, `//`,
`./` and `..`), an absolute path is matched from every segment, and case and Unicode variants
count as the same file. A read is hidden when any path-like argument names an excluded file,
as written or through a symlink, and a grep whose output names one anywhere is withheld
whole. When only text names an excluded file (a header-like line in a diff, or a grep line
that mentions one), the diff or grep is hidden too, and a separate warning lists it so you
can check it by hand. The
[command line page](../cli.md#excluding-files) has the details.

Key each diff in `PullRequest.diffs` (and an output's `diffs`) by one repo-relative file, as
git names it: `secrets/prod.env`, not `b/secrets/prod.env`, and one file's diff per key. A diff
that breaks this still fails closed: if its key or any of its header lines (`diff --git`,
`---`/`+++`, `rename`, `copy`) names an excluded file, the whole diff is hidden, including any
other files under that key.

Excluding a file doesn't count as reviewing it:

- A claim that rests only on an excluded file has no evidence, so it comes out `unverifiable`.
  In strict mode it is dropped. In lenient mode (the default for issues) it is kept, as with any
  claim the shown code can't settle, even when the excluded file would have contradicted it:
  excluding a file never makes a strict gate keep an output, but in lenient mode it can.
- An output about excluded files only (every path it names is excluded) is not graded at all. It
  is dropped in every mode, with one unchecked finding in `reasons` and a `summary` saying every
  file it is about was excluded. Dropping is the conservative choice: attest can't vouch for it.
- `ReviewResult.excluded_files` lists every excluded path, each decision's `omissions` lists its
  excluded files with the reason `excluded`, the injection result's
  `metadata["files_excluded"]` lists the diffs it skipped, and `warnings` says how many files
  were not reviewed.

Exclusions cover file contents only. File paths still appear (in notes, the changed-file list
and `excluded_files`), and the text of a review output is checked as written, so a reviewer
that quoted a secret in its comment still sends that comment to the grading model. In Python,
`review()` warns, rather than refuses, when the pull request edits `.attestignore` or another
file the patterns came from: load exclusions from the base branch in CI.

## Next

- [Review guidelines](guidelines.md): your team's review rules, and the general standard.
- [Writing the review](writing.md): attest as the reviewer.
- [Outputs and decisions](outputs.md): every field of the inputs and the result.
- [Injection in diffs](injection.md): instructions planted in a pull request for the reviewer.
