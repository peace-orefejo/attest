# Architecture

![attest package layers](assets/diagrams/architecture.svg){ .diagram }

attest is split into layers. Imports only point down: entry points use `display` and the
features, features use `core` and `utils`, and `core` never imports anything above it. `tests/core/test_core_boundary.py`
enforces this, so a feature can't quietly become a dependency of the foundation.

## Layers

**Entry points.** `api.py` holds `Attest`, which keeps the provider, model, client and policy
and runs checks with them. `cli/` is the `attest` command, one module per command group in
`cli/commands/`. Both are thin and call into the features.

**Display.** `display/` turns a `Report`, `CheckResult`, `ReviewResult` or `GateDecision` into
the readable view used by `attest.show`, `attest.render` and the CLI.

**Features.** One package per job:

| Package | Job |
|---|---|
| `checks/` | Faithfulness (`verify.py`), tool use, role adherence and prompt injection. `profiles/` holds the prompts for each answer kind. |
| `code_review/` | Code review mode: the adapter from reviewer outputs to runs, evidence budgeting, the gate, injection checks for diffs, review guidelines (`guidelines/`), the one-call `review()` (`review/`), and attest's own reviewer (`writer/`). |
| `policy/` | Project rules: models, loading from YAML or JSON, deterministic and semantic evaluation. |
| `extraction/` | Bounded text extraction from PDFs, images, XML, CSV, HTML and JSON for the injection scan. |
| `scoring/` | `evaluate()`, which runs the selected checks and assembles a `Report`. |
| `adapters/` | Converters from agent frameworks to runs. LangGraph is built in. |

**Foundation.**

| Package | Job |
|---|---|
| `core/` | The data model (`Trajectory`, `Report`, `CheckResult`, `Finding`, `Artifact`), Wilson intervals, and `core/llm/`: providers, model catalog, clients and the structured `call()`. |
| `utils/` | Pure helpers that know nothing about attest's types: unified-diff parsing, hidden-Unicode and encoded-payload scanning. |

## Design rules

- **Tool outputs are the only evidence.** No check reads the agent's `thought` text when
  deciding whether a claim is true.
- **Untrusted text is data.** Anything an attacker could write reaches a judge only inside a
  bounded, escaped, clearly delimited block, framed as content to judge.
- **Prompts are isolated per answer kind.** Each kind owns its prompts in `checks/profiles/`,
  and tests pin the `factual` and `plan` prompts by SHA-256, so work on `code` can't change how
  plain text is graded.
- **Incomplete is not clean.** Content that couldn't be scanned or extracted, or a budget that
  ran out, is reported as incomplete coverage, never as a pass.
- **Clients are lazy.** Deterministic checks never create an API client, so they run with no key.
- **Small files.** Modules stay short and focused, grouped into feature folders. A file that
  grows past a few hundred lines gets split.

## Where things live

| To change | Look in |
|---|---|
| How claims are extracted or verified | `checks/verify.py`, `checks/profiles/` |
| The code review gate | `code_review/gate/` |
| How review guidelines are parsed and checked | `code_review/guidelines/` |
| How large diffs are cut | `code_review/evidence/` |
| Injection patterns | `checks/injection/detectors/`, `checks/injection/packs/` |
| Supported models | `core/llm/catalog.py` |
| CLI commands | `cli/commands/` |
| How results are printed | `display/` |

The design notes behind code review mode and the injection roadmap are under
[Design notes](design/code-review-mode.md).
