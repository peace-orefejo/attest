import os

import pytest

import attest.providers as providers

try:
    from hypothesis import HealthCheck, settings
except ImportError:
    pass
else:
    settings.register_profile("attest", max_examples=40, deadline=None)
    settings.register_profile(
        "ci",
        parent=settings.get_profile("attest"),
        derandomize=True,
        database=None,
        print_blob=True,
        suppress_health_check=[HealthCheck.too_slow],
    )
    settings.register_profile("thorough", max_examples=2000, deadline=None)
    in_ci = os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")
    settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE") or ("ci" if in_ci else "attest"))


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch):
    monkeypatch.setattr(providers, "load_env", lambda: None)
