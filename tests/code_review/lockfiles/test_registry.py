from attest.code_review.evidence.lockfiles import npm, parser_for, summarize_lockfile


def test_lookup_by_basename():
    assert parser_for("web/package-lock.json") is npm.parse
    assert parser_for("npm-shrinkwrap.json") is npm.parse
    assert parser_for("Gemfile.lock") is None


def test_unknown_file_returns_none():
    assert summarize_lockfile("Gemfile.lock", "@@ -1 +1 @@\n-a\n+b\n") is None


def test_unparseable_input_returns_none_instead_of_raising():
    assert summarize_lockfile("package-lock.json", "") is None
    assert summarize_lockfile("go.sum", "@@ -1 +1 @@\n-garbage\n+more garbage\n") is None
    assert summarize_lockfile("yarn.lock", "\x00\x01 binary \xff") is None


def test_summary_keeps_the_given_path():
    diff = "@@ -1,2 +1,2 @@\n-x v1.0.0 h1:abc=\n+x v1.1.0 h1:def=\n"
    summary = summarize_lockfile("services/api/go.sum", diff)
    assert summary is not None
    assert summary.startswith("services/api/go.sum (generated, 2 lines changed; summarized)")
