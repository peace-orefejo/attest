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

Each list item is one rule, numbered `G1`, `G2`, ... and grouped under its heading. Indented
sub-items join the rule above. `guidelines` also accepts markdown text, a list of files, or
rules loaded with `load_guidelines`.

## With no file: the general standard

Without `guidelines`, attest uses a built-in general standard: flag real problems the change
introduces, point to where they are, name the concrete failure, and summarise without judging
the author. The full text is in `src/attest/code_review/guidelines/general.md`.

The general standard guides attest's own reviewer (see [Writing the review](writing.md)). It
is not checked against outputs: without your rules, outputs are checked for faithfulness only.

## How the rules are used

**As evidence.** Your rules are added to each output's evidence as a `read_guidelines` tool
step. An issue such as "This breaks our rule against raw SQL in handlers" can then be graded:
the rule is something the reviewer could see. The general standard is not added as evidence,
because no reviewer was told about it.

**As a conformance check.** With `follow_guidelines=True` (the default), each output is also
checked against the rules. A rule can be reported in two ways:

| Verdict | Severity | When | Effect |
|---|---|---|---|
| `breaks_guideline` | `fail` | The output does what a rule forbids, or calls rule-breaking code acceptable. | Dropped. Listed in `reasons`. |
| `misses_guideline` | `warn` | The output leaves out something a rule asks for, such as a file name. | Kept. Listed in `notes`. |

The check judges only how the output reviews, never whether it is accurate; faithfulness does
that. Reporting code that breaks a rule is not a break: an issue that reports a hard delete
follows a "no hard deletes" rule. Rules under a section heading apply only to the kind of output
that section names.

## Guarding against false breaks

Every report must name a rule that exists and quote the output's own words; reports that don't
are discarded. Because a break drops an output, each one is then confirmed by a second, narrow
model call that asks whether the output itself says rule-breaking code is fine or does what the
rule forbids. Merely describing such code never counts.

## Turning it off

Pass `follow_guidelines=False` (`--no-follow` on the command line) to skip the conformance check.
Your rules are still added as evidence. The check costs one model call per output, plus one per
reported break.
