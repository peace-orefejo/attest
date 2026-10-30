import pytest

import attest.providers as providers


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch):
    monkeypatch.setattr(providers, "load_env", lambda: None)
