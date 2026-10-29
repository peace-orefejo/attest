# Code review mode

AI code reviewers flag false issues and write summaries that don't match the diff. Code review
mode checks each reviewer output against the code it describes, then decides whether to keep it.

![Code review mode](../assets/diagrams/code-review-flow.svg){ .diagram }

attest checks a reviewer's outputs against the code, and drops the ones the code doesn't back.
Put it between your review pipeline and the people who read the results. If you don't have a
reviewer, attest can [write the review itself](writing.md) and check that too.

## The four output types

| Type | Example | Default gate |
|---|---|---|
| `issue` | "`cart_total` reads past the end of `items`." | lenient |
| `diff_summary` | "Adds retry with exponential backoff to `fetch_user`." | strict |
| `group_summary` | "Auth group: moves session checks into middleware across 3 files." | strict |
| `canvas_answer` | Q: "Does this change the public API?" A: "No, only private helpers changed." | strict |

A **lenient** gate drops an output only when the code contradicts it. A **strict** gate also
drops it when the code shown doesn't support it. Issues default to lenient because a real bug
often depends on code the reviewer didn't paste. Summaries and answers are meant to describe
the change, so anything the diff doesn't show is a problem.

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

The result has one decision per output:

```json
{
  "decisions": [
    {
      "index": 0,
      "output_type": "issue",
      "text": "cart_total no longer checks for a missing user, so user.discount raises when user is None.",
      "question": null,
      "keep": true,
      "mode": "lenient",
      "score": 1.0,
      "summary": "2/2 checkable claims grounded.",
      "reasons": [],
      "notes": [],
      "omissions": []
    },
    {
      "index": 1,
      "output_type": "issue",
      "text": "The loop in cart_total uses range(len(items) + 1) and reads past the end of items.",
      "question": null,
      "keep": false,
      "mode": "lenient",
      "score": 0.0,
      "summary": "0/1 checkable claims grounded.",
      "reasons": [
        {
          "severity": "fail",
          "verdict": "unsupported",
          "subject": "The loop in cart_total uses range(len(items) + 1).",
          "reason": "The diff shows 'for item in items:', which iterates directly over items.",
          "evidence": "for item in items:",
          "step": 1,
          "metadata": {}
        }
      ],
      "notes": [],
      "omissions": []
    }
  ],
  "injection": {
    "check": "code_injection",
    "passed": true,
    "summary": "No reviewer-steering text found in the added lines or PR text.",
    "findings": [],
    "metadata": {"verdict": "clean", "coverage_incomplete": false}
  },
  "guidelines": {"name": "REVIEW.md", "rules": [{"id": "G1", "text": "...", "section": "Issues"}]},
  "written": false,
  "kept": [0],
  "dropped": [1]
}
```

For people, `attest.show(result)` prints the same thing as a status line, a table with one row
per output, and the reasons behind each dropped output. `attest.render(result)` returns it as
plain text. From the shell, `attest review` does the same for a JSON file (see
[Command line](../cli.md#attest-review)).

The full script is `examples/code_review_gate.py`:

![Code review gate output](../assets/terminal/code-review-gate.svg){ .terminal }

Options:

| Argument | Default | Meaning |
|---|---|---|
| `outputs` | `None` | The reviewer's outputs. Leave it out and attest [writes the review](writing.md). |
| `guidelines` | `None` | Your review rules: a markdown path, markdown text, or a list of paths. With `None`, outputs are checked for faithfulness only, and attest's own reviewer uses the general standard. |
| `follow_guidelines` | `True` | Check outputs against your rules and drop the ones that break one. Has no effect without `guidelines`. |
| `modes` | `None` | Override the gate mode per output type, e.g. `{"issue": "strict"}`. |
| `deep` | `True` | Confirm injection hits with a model and check which outputs obeyed them. |
| `limits` | `None` | An `EvidenceLimits` budget for large diffs. |
| `answer_kind` | `"code"` | The answer kind used to grade each output. |

### Lower level

`to_run`, `check_code_injection` and `gate` are still public. Use them to build a custom
pipeline, for example to grade with your own `Report` or to gate outputs one at a time.
`attest.code_review.review(pr, outputs, evaluate=...)` is the same one-call function with your
own grading function in place of `Attest`.

## How code is graded

The `code` answer kind reads evidence the way a reviewer should:

- Lines starting with `+` were added, lines starting with `-` were removed and are gone, and
  unmarked lines are unchanged context.
- The language's standard semantics count as evidence. `range(len(xs))` yields only valid
  indices, and 900 seconds is 15 minutes.
- If the run includes `list_changed_files`, that list is complete. A claim that some other file
  changed is unsupported.
- The code wins over comments, docstrings and commit messages. A comment can't make a claim true.
- Recommendations and speculation about intent are dropped before grading.
- A `read_guidelines` step holds the team's [review rules](guidelines.md). They settle what the
  team requires, never what the code does.

## Large changes

Each output's evidence is kept within a budget (`EvidenceLimits`, 12,000 characters per file
and 60,000 per run by default; pass `limits=` to change it):

- Lockfiles (npm, yarn, pnpm, uv, poetry, Cargo, go.sum) are reduced to the package version
  changes they contain.
- Generated and minified files are replaced by a note saying how many lines changed.
- Large hand-written diffs keep whole hunks until the budget runs out, then note what was left
  out.
- The changed-file list is never cut.

Each decision's `omissions` lists the files that had content left out and why, so you can show
it alongside the decision. At the lower level, `to_run_with_omissions` returns the same list.

## Next

- [Review guidelines](guidelines.md): your team's review rules, and the general standard.
- [Writing the review](writing.md): attest as the reviewer.
- [Outputs and decisions](outputs.md): the `ReviewOutput`, `ReviewResult` and `GateDecision` fields.
- [Injection in diffs](injection.md): instructions planted in a pull request for the reviewer.
