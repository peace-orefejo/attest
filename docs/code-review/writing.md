---
description: "Let attest write a pull request review itself, then check and gate its own output like any other AI reviewer."
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

`write_review` makes one model call and returns a list of `ReviewOutput`:

| Output | How many | Evidence |
|---|---|---|
| `issue` | One per real problem the change introduces, or none. | The diff of the file the issue names (or every diff, if it names a file the pull request doesn't change), plus the changed-file list. |
| `diff_summary` | One per changed file. | That file's diff. |
| `group_summary` | One overview of the whole pull request. | Every diff and the changed-file list. Its `group_name` is the pull request's title. |

Each output is scoped to the diffs it is about, so it is graded against the right code.

The writer reviews only what the pull request changes. Large diffs are cut to the same
`EvidenceLimits` budget as grading. The title, description and diffs are treated as data to
review, never as instructions. A pull request with no diffs raises `ValueError`.
