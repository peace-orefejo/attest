---
title: "attest GitHub Action: AI pull request review you can request"
description: "Add attest to a repository as a reviewer: request it like a teammate, comment /attest, or add a label, and it posts only the review comments the diff backs up."
---

# GitHub Action

Add attest to a repository and it reviews pull requests when asked. It writes a review, checks
every comment against the diff, and posts only the ones that hold up. Comments the diff doesn't
back up are never posted.

There are three ways to ask, and you can turn on any of them:

| Ask by | How |
|---|---|
| **Requesting it as a reviewer** | Pick your bot account from the pull request's Reviewers list, like a teammate. Needs a [bot account](#request-it-as-a-reviewer). |
| **Commenting** | Comment `/attest` on the pull request. Only the repository's owner, members and collaborators can. |
| **Labelling** | Add the `attest` label. |

Requesting it is enough: attest reviews straight away, with no comment needed. GitHub tells
the workflow a reviewer was requested, and attest reviews when that reviewer is your bot
account. Comment `/attest` to have it review again after new pushes.

It can also review every pull request when it's opened or updated, and draft pull requests are
skipped.

Each repository uses its own model key, so you pay your model provider directly for the reviews.

## Set it up

1. Add your model key as a repository secret: **Settings → Secrets and variables → Actions →
   New repository secret**, named `ANTHROPIC_API_KEY`.
2. Add this workflow as `.github/workflows/attest.yml`:

```yaml
name: attest review

on:
  pull_request:
    types: [review_requested, labeled]
  issue_comment:
    types: [created]

permissions:
  contents: read
  pull-requests: write

concurrency:
  group: attest-${{ github.event.pull_request.number || github.event.issue.number }}
  cancel-in-progress: true

jobs:
  review:
    # Skip comments that aren't asking, before a runner starts.
    if: >-
      github.event_name != 'issue_comment' ||
      (github.event.issue.pull_request && startsWith(github.event.comment.body, '/attest'))
    runs-on: ubuntu-latest
    steps:
      - uses: peace-orefejo/attest@<full commit SHA>  # vX.Y.Z
        with:
          api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

That turns on commenting and labelling. Reviews are posted as `github-actions[bot]`.

To review every pull request as well, add the automatic types:

```yaml
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review, review_requested, labeled]
```

Replace `<full commit SHA>` with the commit of an
[attest release](https://github.com/peace-orefejo/attest/releases), and keep its version in the
comment. A commit SHA can never point at different code, while a tag can be moved, so you always
know exactly what runs with your key and token. Dependabot recognises this format and opens a
pull request to update both when attest publishes a new release.

## Request it as a reviewer

GitHub only lists people and teams as reviewers, so attest needs an account to be requested as.
Each team uses its own:

1. Create a GitHub account for the bot, such as `yourteam-attest`. On a paid organization plan
   it takes a seat.
2. Invite it to the repository with **write** access, and accept the invitation as the bot.
3. Signed in as the bot, create a
   [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new)
   for the repository with **Pull requests: read and write** and **Contents: read**.
4. Add that token as a repository secret named `ATTEST_BOT_TOKEN`.
5. Pass the bot's login and token to the Action:

```yaml
      - uses: peace-orefejo/attest@<full commit SHA>  # vX.Y.Z
        with:
          api-key: ${{ secrets.ANTHROPIC_API_KEY }}
          reviewer: yourteam-attest
          github-token: ${{ secrets.ATTEST_BOT_TOKEN }}
```

Now requesting `yourteam-attest` as a reviewer starts a review, and the review is posted as the
bot, which completes the request.

## What it posts

One comment-only review. It never approves or requests changes.

- An overview of the change: what it does and how well the approach holds up.
- Each issue that held up as a comment on its line, with a one-click suggestion when the fix
  is one line. Issues no single line shows are listed in the review instead.
- A collapsed file-by-file summary.
- **Check by hand**: text in the pull request that looks aimed at AI reviewers, files GitHub
  sent no diff for (binary or too large), and files left out by `.attestignore`.
- A footer with how many comments attest wrote, how many didn't hold up, and the commit it
  reviewed.

If someone asked for the review and it couldn't be written, for example because the key is
missing, attest posts a short note saying so. A review that ran automatically only logs it.

## Your rules and exclusions

- **Review rules:** put them in `REVIEW.md` at the repository root, or point the `guidelines`
  input at another file. See [review guidelines](code-review/guidelines.md). Without one,
  attest's general standard applies.
- **Exclusions:** files matching `.attestignore` are never sent to the model. See
  [leaving files out](code-review/index.md#leaving-files-out).

Both are read from the pull request's **base branch**, so a pull request can't change the
rules it is reviewed by.

## Security

- attest never checks out or runs the pull request's code. It reads the diff through the GitHub
  API.
- The pull request's title, description, commits and diffs are treated as data to review, never
  as instructions. Text planted to steer AI reviewers is scanned for, and comments it may have
  influenced are dropped ([injection in diffs](code-review/injection.md)).
- Only the owner, members and collaborators can start a review by comment, so strangers can't
  spend your model credits.
- **Forks:** GitHub doesn't give `pull_request` workflows secrets for pull requests from forks.
  Ask for those reviews by comment, which runs in your repository with your secrets. Using
  `pull_request_target` also works, because attest never runs the pull request's code.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `api-key` | | Model API key, from a secret. Required. |
| `provider` | `anthropic` | `anthropic`, `openai` or `gemini`. |
| `model` | the provider's default | Model name. See [models and providers](providers.md). |
| `reasoning` | `auto` | `auto`, `off`, `low`, `medium` or `high`. |
| `github-token` | `github.token` | Token used to read the pull request and post the review. |
| `reviewer` | | Your bot account's login. Requesting it starts a review. |
| `command` | `/attest` | A comment starting with this starts a review. If you change it, change the workflow's `if:` too. |
| `label` | `attest` | Adding this label starts a review. |
| `guidelines` | `REVIEW.md` if it exists | Your review rules on the base branch. |
| `attestignore` | `true` | Read `.attestignore` from the base branch. |
| `fail-on-error` | `false` | Fail the job when the review can't be written. |

## Outputs

| Output | Meaning |
|---|---|
| `reviewed` | `true` when a review was posted. |
| `kept` | How many comments were posted. |
| `dropped` | How many didn't hold up and weren't posted. |
| `review-url` | Link to the review. |
