# Outputs and decisions

## ReviewOutput

One thing the reviewer produced, with the evidence it was based on.

```python
ReviewOutput(
    output_type="issue",
    text="cart_total reads past the end of items.",
    diffs={"billing/cart.py": "--- a/billing/cart.py\n+++ b/billing/cart.py\n@@ ..."},
    changed_files=["billing/cart.py"],
    reads=[FileRead(arguments={"path": "billing/models.py"}, output="class Item: ...")],
)
```

| Field | Meaning |
|---|---|
| `output_type` | `issue`, `diff_summary`, `group_summary` or `canvas_answer`. |
| `text` | What the reviewer said. |
| `diffs` | Unified diff for each file the output talks about, keyed by path. |
| `changed_files` | Every file the pull request touched. Lets attest catch "this PR also changes X". Leave it as `None` if you don't know the full list. |
| `reads` | Extra source the reviewer looked at, as `read_file` or `grep` results. |
| `question` | The question, for a `canvas_answer`. |
| `group_name` | The group's name, for a `group_summary`. |

If `diffs` is empty or `changed_files` is `None`, `review()` fills them from the pull request.

`paths()` lists every file the output's evidence covers. `review()` passes it to `gate()` so
injection findings in unrelated files don't affect this output.

## PullRequest

The whole change. `review()` scans it for injection, and attest's own reviewer writes from it.

| Field | Meaning |
|---|---|
| `diffs` | Diff for every changed file. |
| `changed_files` | Every changed path. |
| `title`, `description`, `commit_messages` | Author-written text, which is also scanned for planted instructions. |

## ReviewResult

`review()` returns one `ReviewResult` for the whole pull request.

| Field | Meaning |
|---|---|
| `decisions` | One `OutputDecision` per output, in order. |
| `injection` | The `code_injection` check result for the pull request. |
| `guidelines` | The `ReviewGuidelines` used: your rules, or the general standard (`builtin=True`). |
| `written` | `True` when attest wrote the outputs itself. |
| `warnings` | Things to check by hand, e.g. the pull request changes the file its review rules came from. |
| `kept` | Indexes of the outputs to keep. |
| `dropped` | Indexes of the outputs to drop. |

`filter(outputs)` returns the kept outputs in their original order. With no argument it returns
the kept outputs from the ones `review()` checked, which is how you get attest's own review when
`written` is `True`. Passing a list of a different length raises `ValueError`.

`kept` and `dropped` are included in `model_dump()` and `model_dump_json()`. The outputs
themselves are not.

## OutputDecision

| Field | Meaning |
|---|---|
| `index` | Position of the output in the list. |
| `output_type` | `issue`, `diff_summary`, `group_summary` or `canvas_answer`. |
| `text` | What the output said. |
| `question` | The question, for a `canvas_answer`. |
| `paths` | The files the output was checked against. |
| `keep` | Show the output (`True`) or hide it (`False`). |
| `mode` | The gate mode used. |
| `score` | The faithfulness score, or `None` when no claim could be checked. |
| `summary` | The faithfulness summary, e.g. "2/2 checkable claims grounded." |
| `reasons` | The findings that dropped it. Empty when kept. |
| `notes` | Findings shown alongside it that did not drop it. |
| `omissions` | Files whose content was left out of the evidence, with the reason. |

## GateDecision

`gate()` decides for one output. `review()` calls it for you; call it yourself in a custom
pipeline.

```python
GateDecision(
    keep=False,
    mode="lenient",
    reasons=[
        Finding(
            verdict="unsupported",
            subject="The loop in cart_total uses range(len(items) + 1) and reads past the end of items.",
            reason="The code shows 'for item in items:', which iterates directly over items.",
            evidence="for item in items:",
        )
    ],
    notes=[],
)
```

| Field | Meaning |
|---|---|
| `keep` | Show the output (`True`) or hide it (`False`). |
| `mode` | The gate mode used: the default for the output type, or the `mode=` you passed. |
| `reasons` | What dropped the output: each failing claim, each broken rule of yours, and each injection finding that blocks it. Empty when kept. |
| `notes` | Findings shown alongside the output that did not drop it: a guideline it missed (`misses_guideline`), a `suspicious` hit in its files, or a `compromised` finding in its files that affected a different output. |

What drops an output:

| Source | Lenient | Strict |
|---|---|---|
| Faithfulness `unsupported` | drop | drop |
| Faithfulness `unverifiable` | keep | drop |
| One of your rules broken (with `follow_guidelines=True`) | drop | drop |
| Guideline missed (with `follow_guidelines=True`) | keep, listed as a note | keep, listed as a note |
| Injection `payload` in this output's files | drop | drop |
| Injection `compromised`, this output affected | drop | drop |
| Injection `compromised`, another output affected | keep, listed as a note | keep, listed as a note |
| Injection `suspicious` | keep, listed as a note | keep, listed as a note |

Injection findings in files outside the output's `paths()` are ignored. Override the mode with
`review(..., modes={"issue": "strict"})` or `gate(report, "issue", mode="strict")`.
