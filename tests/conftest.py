import pytest

import attest.core.llm.env as env


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch):
    monkeypatch.setattr(env, "load_env", lambda: None)
