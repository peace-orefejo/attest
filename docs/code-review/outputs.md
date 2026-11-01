---
title: "Code review outputs and gate decisions"
description: "Reference for attest's code review types: ReviewOutput, PullRequest, ReviewResult, OutputDecision and GateDecision."
---

# Outputs and decisions

## ReviewOutput

One thing the reviewer produced, with the evidence it was based on.

```python
from attest.code_review import FileRead, ReviewOutput

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
| `changed_files` | The whole pull request's list of changed files, not just this output's. Lets attest catch a wrong "this PR also changes X". Usually left out: `review()` copies it from the pull request. |
| `reads` | Other code the reviewer looked at. Each `FileRead` has a `tool` (`read_file`, the default, or `grep`), its `arguments` and its `output`. |
| `question` | The question, for a `canvas_answer`. |
| `group_name` | The group's name, for a `group_summary`. |

If `diffs` is empty or `changed_files` is `None`, `review()` fills them from the pull request.

`paths()` lists every file the output's evidence covers, so injection findings in unrelated
files don't affect it.

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

You only see this type if you call `gate()` yourself. `OutputDecision` above is the same
decision plus the output's identity and scores.

| Field | Meaning |
|---|---|
| `keep` | Show the output (`True`) or hide it (`False`). |
| `mode` | The gate mode used: the default for the output type, or the `mode=` you passed. |
| `reasons` | What dropped the output: each failing claim, each broken rule of yours, and each injection finding that blocks it. Empty when kept. |
| `notes` | Findings shown alongside the output that did not drop it: a guideline it missed (`misses_guideline`), a `suspicious` hit in its files, or a `compromised` finding in its files that affected a different output. |

## What drops an output

| Source | Lenient | Strict |
|---|---|---|
| Faithfulness `unsupported` | drop | drop |
| Faithfulness `unverifiable` | keep | drop |
| A claim no model judged (a failed call, `metadata["checked"]` is `false`) | drop | drop |
| More claims than `max_claims` (40 by default): each claim past the cap is unchecked | drop | drop |
| One of your rules broken (with `follow_guidelines=True`) | drop | drop |
| Guideline missed (with `follow_guidelines=True`) | keep, listed as a note | keep, listed as a note |
| Injection `payload` in this output's files | drop | drop |
| Injection `compromised`, this output affected | drop | drop |
| Injection `compromised`, another output affected | keep, listed as a note | keep, listed as a note |
| Injection `suspicious` | keep, listed as a note | keep, listed as a note |

An output past the claim cap lists each unchecked claim in `reasons`, and its `summary` says how
many were not checked. Raise the cap with `review(..., max_claims=60)` or `attest review
--max-claims 60`.

Injection findings in files outside the output's `paths()` are ignored. Override the mode with
`review(..., modes={"issue": "strict"})` or `gate(report, "issue", mode="strict")`.
