---
title: "Check an AI review bot's comments in one call"
description: "Use attest in your AI code review bot: pass the git diff and the bot's comments to check_findings() and post only the ones the diff supports."
---

# In your review bot

If you already have a review bot and only want to know which of its comments to post, you need
one function. Pass the change and what the bot said; get back keep or drop, with a reason.

```python
from attest import check_findings

results = check_findings(
    diff,  # the output of `git diff base...head`
    ["cart_total no longer checks for a missing user, so user.discount raises when user is None.",
     "The loop in cart_total reads one past the end of items."],
)

for r in results:
    if r.keep:
        post_comment(r.text)
    else:
        print("dropped:", r.text, "-", r.reason)
```

It needs a model key, like every check that calls a model: set `ANTHROPIC_API_KEY`, or pass
`key=`, `provider=` and `model=` (see [models and providers](../providers.md)).

## Answers to questions

If people ask your bot questions about the change, pass the answers too. They come back after
the findings, with their `question` set.

```python
results = check_findings(
    diff,
    findings,
    answers={"Does this change the public API?": "No, only private helpers changed."},
)
```

Answers are held to a stricter bar than findings: an answer is kept only when the diff clearly
backs it, while a finding is kept unless the diff contradicts it. A real bug often depends on
code outside the diff; an answer about the change shouldn't.

## What you get back

One `CheckedFinding` per finding, then one per answer, in the order you passed them.

| Field | Meaning |
|---|---|
| `text` | The finding or answer. |
| `question` | The question, for an answer; otherwise `None`. |
| `keep` | `True` when the diff backs it up. Post it only then. |
| `reason` | One line: the check's summary when kept, or the first thing that dropped it. |
| `reasons` | Every finding that dropped it, one line each. Empty when kept. |

## Options

| Option | Default | Meaning |
|---|---|---|
| `diff` | | `git diff` output, or a `{path: diff}` mapping. |
| `findings` | `()` | The bot's comments, as a list of strings. |
| `answers` | `None` | `{question: answer}`. |
| `guidelines` | `None` | Your [review rules](guidelines.md), as markdown text or a path. When given, anything that breaks them is dropped too. Without them, no rules check runs, which saves a model call per comment. |
| `provider`, `model`, `key` | Anthropic, its default model, the environment | Which model checks the comments. |
| `attest` | `None` | An `Attest` you built yourself, to set anything else: [exclusions](index.md#leaving-files-out), a budget, caching, reasoning. |

The pull request is also scanned for planted instructions aimed at AI reviewers, and a comment
that obeyed one is dropped ([injection in diffs](injection.md)).

## When you need more

`check_findings` covers the common case. Use [`Attest().review`](index.md) when you want
per-file summaries, the files your bot read, the injection result, or attest to
[write the review](writing.md) itself.
