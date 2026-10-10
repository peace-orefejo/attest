import attest


def test_bare_import_keeps_legacy_submodule_attributes():
    assert attest.trajectory.Trajectory is attest.Trajectory
    assert attest.results.Report is attest.Report
    assert attest.content.Artifact is attest.Artifact
    assert callable(attest.providers.list_models)
