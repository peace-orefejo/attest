# Review guidelines

Most teams have rules for code review: what to flag, what to leave alone, how to word a
comment. Write them in a markdown file and pass it to `review()`. attest checks every output
against them, drops the ones that break a rule, and notes the ones that leave out something a
rule asks for.

```python
from attest import Attest

result = Attest().review(pr, outputs, guidelines="REVIEW.md")
```

## Write the file

Each list item is a rule. Headings group them.

```markdown
# Review rules

## Issues
- Only flag problems the pull request introduces.
- Do not flag naming or formatting.
- Name the file and the function an issue is about.
- Security issues must say who can trigger them:
  - an anonymous user, a signed-in user, or an admin.

## Summaries
- Say what changed, not why the author changed it.
- Mention every migration in `db/migrations/`.
```

attest reads this as six rules:

| Id | Section | Rule |
|---|---|---|
| G1 | Issues | Only flag problems the pull request introduces. |
| G2 | Issues | Do not flag naming or formatting. |
| G3 | Issues | Name the file and the function an issue is about. |
| G4 | Issues | Security issues must say who can trigger them: an anonymous user, a signed-in user, or an admin. |
| G5 | Summaries | Say what changed, not why the author changed it. |
| G6 | Summaries | Mention every migration in db/migrations/. |

How the file is parsed:

- Every list item (`-`, `*`, `+` or `1.`) is one rule, numbered `G1`, `G2`, ... in order.
- A rule belongs to the nearest heading above it.
- Indented sub-items and indented continuation lines join the rule above them.
- Bold and code markers are removed. HTML comments are ignored.
- A file with no list items uses each paragraph as a rule instead.
- A file with no rules at all raises `ValueError`.
- At most 200 rules are read, each up to 1,000 characters.

`guidelines` takes:

| Value | Meaning |
|---|---|
| `None` | The built-in general standard. |
| `"REVIEW.md"` or a `Path` | A markdown file (`.md`, `.markdown` or `.txt`). |
| A markdown string | The rules themselves. |
| A list of paths | Several files, merged and renumbered `G1`, `G2`, ... |
| A `ReviewGuidelines` | Rules you already loaded with `load_guidelines`. |

```python
from attest.code_review import load_guidelines

rules = load_guidelines(["REVIEW.md", "SECURITY_REVIEW.md"])
print(rules.render())
```

## With no file: the general standard

Without `guidelines`, attest uses its built-in general standard:

**Issues**

- G1: Flag bugs, security problems, data loss and behaviour changes caused by what the pull
  request adds, removes or changes, including removed checks. Do not flag pure style or
  formatting unless it hides a bug.
- G2: An issue is about code the pull request adds, removes or changes, not code it leaves
  untouched.
- G3: Point to where an issue is: the file, function or line.
- G4: An issue names a concrete failure, such as an exception, a wrong value or lost data,
  rather than only saying something "might be a problem".
- G5: Report each problem once.

**Summaries and answers**

- G6: A summary says what the change does. It does not judge the author or guess at their intent.
- G7: A summary covers the main changes and does not mention changes that are not in the diff.
- G8: An answer to a question answers it directly before adding detail.

**Tone**

- G9: Be specific and neutral: no insults, sarcasm or filler praise.

The file is `src/attest/code_review/guidelines/general.md`. In the result, its name is
`general standard` and `builtin` is `True`.

The general standard guides attest's own reviewer (see [Writing the review](writing.md)). It
is not checked against outputs: without your rules, outputs are checked for faithfulness only.
In testing, checking outputs against the general standard flagged correct issues (a removed auth
check read as "not introduced", a units bug read as "speculative") and caught nothing
faithfulness didn't. If you call `check_guidelines` with it directly, its findings are notes
that never drop an output.

## How the rules are used

**As evidence.** Your rules are added to each output's evidence as a `read_guidelines` tool
step. An issue such as "This breaks our rule against raw SQL in handlers" can then be graded:
the rule is something the reviewer could see. The general standard is not added as evidence,
because no reviewer was told about it.

**As a conformance check.** With `follow_guidelines=True` (the default), each output is also
checked against the rules. A rule can be reported in two ways:

| Verdict | Severity | When | Effect |
|---|---|---|---|
| `breaks_guideline` | `fail` | The output does what a rule says not to do (flags or asks for what the rules say not to), or says code that breaks a rule is acceptable, or recommends such code. | Dropped, whatever the gate mode. Listed in `reasons`. |
| `misses_guideline` | `warn` | The output leaves out something a rule asks every output of its kind to include, such as a file name. | Kept. Listed in `notes`. |

The check judges only how the output reviews, never whether it is accurate; faithfulness does
that. Describing or reporting code that breaks a rule is not a break: an issue that reports a
hard delete follows a "no hard deletes" rule. Leaving other problems out is never a break or a
miss, and rules under a section heading apply only to the kind of output that section names.

Each finding names the rule:

```json
{
  "severity": "fail",
  "verdict": "breaks_guideline",
  "subject": "G2: Do not flag naming or formatting.",
  "reason": "The issue only asks for a variable to be renamed.",
  "evidence": "rename tmp to subtotal",
  "metadata": {"rule": "G2", "section": "Issues", "source": "REVIEW.md"}
}
```

The `guidelines` check passes unless a rule is broken. Its summary counts both kinds, for
example "Breaks 1 and misses 1 of 9 rules in REVIEW.md."

## The exact-quote guard

The model that checks conformance must give, for each report, a rule id that exists and a quote
from the output: the words that break the rule, or for a miss, the sentence that should have
included what the rule asks for. attest then checks the quote against the output text (ignoring
case and whitespace). The quote must be at least three words, or the whole output. A report that
names an unknown rule (ids are case-insensitive), or quotes words the output doesn't contain, is
discarded and counted in the check's `metadata["discarded"]`. Each rule is reported at most
once per output, and a break hides a miss of the same rule.

## Confirming breaks

A break drops an output, so each one gets a second, narrow model call before it counts. That
call answers three separate questions about the output's own words:

| Question | Counts as a break? |
|---|---|
| Does it report or describe code that does what the rule forbids? | No. Reporting problems is the reviewer's job. |
| Does it say such code is fine, or recommend writing it? | Yes. |
| Is the rule about how to review, and does the output itself do what it forbids? | Yes. |

A break that isn't confirmed is discarded and counted in `metadata["unconfirmed"]`. Asking the
three questions apart matters: asked as one question, small models read "the summary mentions
an f-string query" as breaking a "no f-string SQL" rule. In testing on 9 outputs against a
7-rule REVIEW.md, the one-question check dropped 3 to 4 of the 5 correct outputs; with
confirmation it dropped none, and still caught all 4 real breaks (flagging formatting,
suggesting a rename, asking for tests, calling an f-string query acceptable).

So an output is never dropped for a rule it didn't break in its own words, and reporting code
that breaks a rule is never a break. Rules that don't apply to the kind of output are not
reported.

## Turning it off

```python
result = Attest().review(pr, outputs, guidelines="REVIEW.md", follow_guidelines=False)
```

With `follow_guidelines=False`, no conformance check runs: no output is dropped for breaking a
rule and no misses are noted. Your rules are still added as evidence. On the command line, use `--no-follow`.

## Cost

With your rules, the conformance check is one extra model call per output, plus one per reported
break. Without rules there is no conformance check. Turn it off with `follow_guidelines=False`
when you only need faithfulness.
