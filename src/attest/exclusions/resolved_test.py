"""A path's forms: as written, and with symlinks resolved relative to the current directory."""

from attest.exclusions import path_forms, within_cwd


def test_a_link_resolves_to_its_target_inside_the_current_directory(tmp_path, monkeypatch):
    (tmp_path / "secrets").mkdir()
    (tmp_path / "docs").symlink_to("secrets")
    monkeypatch.chdir(tmp_path)
    assert path_forms("docs/k.env") == ["docs/k.env", "secrets/k.env"]
    assert path_forms(f"{tmp_path}/docs") == ["docs", "secrets"]


def test_a_plain_path_has_one_form_and_outside_paths_stay_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert path_forms("app/main.py") == ["app/main.py"]
    assert within_cwd("/elsewhere/k.env", [tmp_path]) == "/elsewhere/k.env"
    assert path_forms("bad\x00name") == ["bad\x00name"]
