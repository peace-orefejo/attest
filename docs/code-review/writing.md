---
title: "Writing a pull request review with attest"
description: "Let attest write an AI pull request review itself, then check every comment against the diff and gate its own output like any other AI reviewer."
---

# Writing the review

attest can review a pull request itself. It follows a built-in
[general standard](guidelines.md#with-no-file), and your [review rules](guidelines.md) add to it
and win where they conflict. Its review gets no special treatment: each output is then graded,
checked against your rules and gated like any other reviewer's, and `result.written` is `True`.

## Three ways to run it

Write the review only, without checking it:

```python
from attest import Attest

outputs = Attest().write_review(pr, guidelines="REVIEW.md")
```

Write it and check it in one call, by leaving out `outputs`:

```python
result = Attest().review(pr, guidelines="REVIEW.md")
result.written    # True
result.filter()   # the outputs attest wrote and kept
```

From the shell, put only the pull request in the review file, `pr.json`:

```json
{"pr": {"title": "Apply the user's discount", "diffs": {"billing/cart.py": "--- a/billing/cart.py\n..."}}}
```

```bash
attest review pr.json -g REVIEW.md
```

## What it produces

`write_review` works in three steps, always in this order, each building on the last:

1. **Understand.** What each changed file now does, and how it connects to the others.
2. **Design.** What the whole change does, and where the approach is risky for correctness,
   security, performance or maintainability.
3. **Findings.** The concrete problems, each on its line, with a one-line fix where there is one.

Every step reads the same evidence (your rules, the pull request and its diffs, with line
numbers), sent once so provider prompt caches can reuse it. When `review()` writes the review,
it checks each summary and the overview before the next step builds on them, so a misreading of
the code is not carried forward; those checks are reused when the outputs are gated, so nothing
is graded twice. Call `write_review(pr, check=...)` to pass your own check.

It returns a list of `ReviewOutput`:

| Output | How many | Evidence |
|---|---|---|
| `issue` | One per real problem the change introduces, or none. Its `line` is the line it is about, in the new version of the file, and its `suggestion` the corrected text of that line when the fix is that small. Both are `None` otherwise, or when the line isn't an added or unchanged line of the diff. | The diff of the file the issue names (or every diff, if it names a file the pull request doesn't change), plus the changed-file list. |
| `diff_summary` | One per changed file. | That file's diff. |
| `group_summary` | One overview of the whole pull request: what it does and how well the approach holds up, in up to three short paragraphs. | Every diff and the changed-file list. Its `group_name` is the pull request's title. |

Each output is scoped to the diffs it is about, so it is graded against the right code.

The writer reviews only what the pull request changes. Large diffs are cut to the same
`EvidenceLimits` budget as grading. The title, description and diffs are treated as data to
review, never as instructions. A pull request with no diffs raises `ValueError`.
