"""
Shared pytest configuration for the fta_web test suite.

Puts ``fta_web/core`` on ``sys.path`` so the vendored modules import under
their bare names (``FTA_Editor_core``, ``AI_agent_handler``, ``ai_providers``,
``json_viewer``).

Bare names are mandatory, not stylistic: ``fta_web/core/AI_agent_handler.py``
does ``from ai_providers import AIProviderFactory`` at module level, so
``fta_web.core.*`` package imports would break on that line.

This insertion happens at conftest import time -- before any test module is
imported -- so the individual test files need no ``sys.path`` boilerplate.
"""
import sys
from pathlib import Path

import pytest

# fta_web/tests/conftest.py -> parents[0]=tests, [1]=fta_web, [2]=repo root
TESTS_DIR = Path(__file__).resolve().parent
FTA_WEB_DIR = TESTS_DIR.parent
REPO_ROOT = FTA_WEB_DIR.parent
CORE_DIR = FTA_WEB_DIR / "core"

if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path to the repository root."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def core_dir() -> Path:
    """Absolute path to the vendored core package directory."""
    return CORE_DIR


@pytest.fixture(scope="session")
def sample_fta_path() -> Path:
    """Path to the vendored sample FTA tree used by the export tests."""
    path = FTA_WEB_DIR / "examples" / "sampleFTA.json"
    if not path.exists():
        pytest.fail(f"Vendored sample data missing: {path}")
    return path


@pytest.fixture
def fta_core():
    """A fresh, empty FTACore instance."""
    from FTA_Editor_core import FTACore

    return FTACore()
