# Benchmark reports

`run.py --out` writes JSON reports here. Ad-hoc reports are ignored by git (see `.gitignore`),
so experiments don't end up in commits.

A report that backs a published result is committed deliberately, under `published/`, named for
what it is, for example `published/0.9.0-heldout-anthropic-claude-haiku-5-5.json`. Commit it
together with the dataset version it was run on (the report records it), and only once every
case it covers has `label_status: "confirmed"`.
