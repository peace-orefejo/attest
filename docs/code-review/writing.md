# Writing the review

attest can review a pull request itself. It always follows the general standard as a baseline,
and your [guidelines](guidelines.md) add to it and win where they conflict. Its review is then
checked and gated like any other reviewer's.

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

From the shell, leave `outputs` out of the review file:

```bash
attest review pr.json -g REVIEW.md
```

```json
{"pr": {"title": "Apply the user's discount", "diffs": {"billing/cart.py": "--- a/billing/cart.py\n..."}}}
```

## What it produces

`write_review` makes one model call and returns a list of `ReviewOutput`:

| Output | How many | Evidence |
|---|---|---|
| `issue` | One per real problem the change introduces, or none. | The diff of the file it names (every diff if that file isn't in the pull request), plus the changed-file list. |
| `diff_summary` | One per changed file. | That file's diff. |
| `group_summary` | One overview of the whole pull request. | Every diff and the changed-file list. Its `group_name` is the pull request's title. |

Each output is scoped to the diffs it is about, so it is graded against the right code.

The writer reviews only what the pull request changes. Large diffs are cut to the same
`EvidenceLimits` budget as grading. The title, description and diffs are treated as data to
review, never as instructions. A pull request with no diffs raises `ValueError`.

## Checked like any reviewer

attest's own outputs get no special treatment. In `review()` each one is graded for
faithfulness, checked against the guidelines, and gated, and an output that fails is dropped.
When attest wrote the outputs, `written` is `true` in the result.
