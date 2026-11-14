"""Fixtures of the F4 (What-if sliders) acceptance tests.

Everything is local to this directory: the fixtures below are visible to the tests
beside this file only. ``fta_web.whatif`` is imported by the tests that need it,
inside the test; the one fixture that tidies its cache tolerates the module not
existing yet (so that the tests fail on what they check, not at setup).
"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import whatif_support as W  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Credentials and the recovery folder live in this test's temp folder."""
    from AI_agent_handler import AICredentialManager

    directory = tmp_path / "fta_editor_home"
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_DIR", directory)
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_FILE", directory / "ai_credentials.json")
    yield directory
    from fta_web import recovery

    recovery.end_session()


@pytest.fixture(autouse=True)
def _fresh_caches():
    """The diagram remembers the headline of the last document it saw, and the
    what-if keeps one baseline: a test must not meet an earlier one."""
    from fta_web import engine

    def clear():
        cache = getattr(engine, "_headline_cache", None)
        if cache is not None:
            cache[:] = []
        module = W.whatif_module_if_built()
        if module is not None:
            module.clear_cache()

    clear()
    yield
    clear()


@pytest.fixture
def client(tmp_path):
    from fta_web.state import reset_state

    app = W.make_app(tmp_path)
    with app.test_client() as test_client:
        yield test_client
    reset_state()


@pytest.fixture
def api(client, tmp_path):
    return W.Api(client, tmp_path)


@pytest.fixture
def r1(api):
    """The R1 document is open (A, B under an AND, beta group g1)."""
    api.open_doc(W.r1_doc())
    return api


@pytest.fixture
def models(api):
    """The four-model tree (RATE, STBY, REPA, FIX) is open."""
    api.open_doc(W.models_doc())
    return api
