# Contributing to attest

Thanks for helping. This guide covers setting up, the rules the codebase follows, and how to get a
change merged.

## Set up

attest uses [uv](https://docs.astral.sh/uv/) and supports Python 3.11 to 3.13.

```bash
git clone https://github.com/peace-orefejo/attest.git
cd attest
uv sync                      # library, dev tools and every optional extra
uv run pytest                # the whole suite runs offline, no API key needed
```

Image OCR tests also need the `tesseract` executable (`brew install tesseract` or
`apt install tesseract-ocr`). Without it they are skipped.

To try a change against a real model, put a key in a `.env` file at the repo root and run:

```bash
uv run attest run examples/trajectory.json
uv run python examples/code_review_gate.py
```

## Run what CI runs

CI tests Python 3.11, 3.12 and 3.13 with only the core dependencies, and Python 3.13 with the
`files` extra. It also builds the package and the docs. To check the same things locally:

```bash
uv run pytest -q
GITHUB_ACTIONS=true uv run pytest -q        # the CLI forces color under Actions
uvx ruff check src examples benchmarks && uvx ruff format --check src examples benchmarks
uv run pyright                              # strict; can take a few minutes
uv build && uvx twine check dist/*
uv run --group docs mkdocs build --strict
```

A core-only run catches code that imports an optional dependency without guarding it:

```bash
uv venv /tmp/attest-core --python 3.11
uv pip install --python /tmp/attest-core -e . pytest
/tmp/attest-core/bin/python -m pytest -q
```

## How the code is organised

The package is layered. Imports only point down:

- **Entry points:** `api.py` and `cli/`. The CLI prints only JSON.
- **Features:** `checks/`, `code_review/`, `policy/`, `extraction/`, `scoring/` and `adapters/`.
- **Foundation:** the data models (`trajectory.py`, `results.py`, `content.py`),
  `disposition_rules.py` for how findings map to pass, review or block, `providers.py`, `llm/`
  for model calls, caching and budgets, and `prompts/` for every prompt.
- **Helpers:** `utils/`, small stateless helpers shared by several features.

The foundation never imports from a feature package.

The [architecture page](https://peace-orefejo.github.io/attest/architecture/) says where each
kind of change belongs.

## Rules for code

- **Keep files small.** Aim for well under 200 lines per module. Split a growing module into a
  feature folder with focused files, and move generic helpers into `utils/`.
- **Name things clearly instead of commenting.** Comments are rare in this codebase. Add one
  only when the code can't explain itself, such as a non-obvious constraint. Docstrings on
  public functions are welcome, since they appear in the API reference.
- **Read top-down.** Entry functions tell the story in a few calls and return early on guard
  cases. Helpers are small, stateless and do one thing.
- **Use typed, structured values.** Use `from __future__ import annotations` and Pydantic models
  rather than dataclasses, tuples or loose dicts. Use built-in generics and `X | None`. Avoid
  `Any` and `# type: ignore`; the code must pass strict pyright.
- **Put prompts in `prompts/`.** Never write prompt text inline in a feature module.
- **Keep the public API stable.** Anything exported from `attest` or `attest.code_review` is
  public, as are module paths such as `attest.trajectory` and `attest.checks.injection`.
- **Never trust what the agent says.** A check must judge against tool outputs, never the
  agent's reasoning.
- **Treat untrusted text as data.** Text from tool outputs, artifacts or diffs reaches a judge
  only through the bounded, escaped framing helpers.
- **Don't report incomplete coverage as clean.** If content couldn't be scanned or a budget
  ran out, say so in the result.
- **Guard optional dependencies.** Import `pypdf`, `PIL`, `pytesseract`, `zxingcpp`,
  `defusedxml` and `google-genai` only inside the function that needs them, and degrade
  gracefully when they're missing. `import attest` must work with only the core dependencies.

## Changing prompts

All prompts live in `src/attest/prompts/`. Grading prompts are in `prompts/profiles/`, one module
per answer kind. `prompts/profiles/profiles_test.py` pins the `factual` and `plan` prompts by
SHA-256, so editing one kind can't silently change another.

If you change a prompt on purpose:

1. Update its pinned hash in the test, and say why in your pull request.
2. Bump `PROMPT_VERSION` in `src/attest/prompts/version.py`.
3. Rerun the relevant eval and include the before and after numbers. For code review prompts:

   ```bash
   uv run python examples/code_review_eval.py --compare
   ```

## Tests

- Every change needs tests, and they must run offline. Stub model calls by passing fake
  `extract` or `verify` functions, or by monkeypatching `call`. See
  `src/attest/checks/verify_test.py`.
- Put tests next to the code. Tests for `src/attest/foo/bar.py` go in
  `src/attest/foo/bar_test.py`. The built package leaves test files out.
- Labeled cases live in a `fixtures/` folder next to the tests that use them, such as
  `src/attest/code_review/fixtures/`. Add a case when you fix a grading mistake, so it stays
  fixed.

## Docs

The site is built with MkDocs Material from `docs/`, and the API reference is generated from
docstrings.

```bash
uv run --group docs mkdocs serve         # live preview at http://127.0.0.1:8000
uv run --group docs mkdocs build --strict
```

Add a new page to `nav` in `mkdocs.yml`. The strict build fails on broken links and on pages
missing from the nav.

Every CLI command prints JSON through `src/attest/cli/json_output.py`. When you change what a
command prints, or a model it prints (`CheckResult`, `Report`, `ReviewResult` and so on),
regenerate the published schemas; a test fails until they match:

```bash
uv run python docs/scripts/write_schemas.py
```

Adding a field is fine within a schema version. Removing or renaming one, or changing its
meaning, needs a new `SCHEMA_VERSION` and a changelog entry.

Diagrams in `docs/assets/diagrams/` are hand-written SVG. Keep their colors on their own light
background so they read in both themes.

## Send a change

1. Open an issue first for anything bigger than a bug fix, so we can agree on the approach.
2. Branch from `main`. Use a prefix that says what the change is, such as `feat/`, `fix/`,
   `docs/` or `ci/`.
3. Write commit messages in the same style: `feat: add grep evidence to the code adapter`.
4. Add a line under `Unreleased` in `CHANGELOG.md` for any change a user would notice.
5. Open a pull request against `main`. Describe what changed, why, and how you tested it.

## Releases

Maintainers release by bumping the version in `pyproject.toml` and `src/attest/__init__.py`,
moving the `Unreleased` changelog entries under the new version, and publishing a GitHub
release. The publish workflow uploads to PyPI with trusted publishing.

## Reporting security issues

If you find a way to make attest's own grader follow injected instructions, or any other
security problem, please don't open a public issue. Use
[GitHub's private vulnerability reporting](https://github.com/peace-orefejo/attest/security/advisories/new)
instead.
