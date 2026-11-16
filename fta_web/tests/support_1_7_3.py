"""
Fixtures and helpers shared by the release 1.7.3 tests
(``test_release_1_7_3_links.py``, ``_context.py`` and ``_headline.py``).

Not a test module. Each of the three does ``from ...support_1_7_3 import *``,
which also brings the fixtures in -- the two ``autouse`` ones included.

No test reaches the network: the provider is mocked at the instance, as in
``test_api_ai.py``, and the credentials file is redirected to ``tmp_path``.
"""
import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from AI_agent_handler import AICredentialManager, AIProposedChange  # noqa: E402
from ai_providers import AIProviderFactory  # noqa: E402

from fta_web import ai_bridge, engine  # noqa: E402
from fta_web.engine import WebCore  # noqa: E402
from fta_web.numfmt import format_prob  # noqa: E402
from fta_web.state import get_state, reset_state  # noqa: E402

EXAMPLES = REPO_ROOT / "fta_web" / "examples"
CHALLENGER = EXAMPLES / "challenger_fta_en.json"
CHALLENGER_JA = EXAMPLES / "challenger_fta_ja.json"
TMI = EXAMPLES / "tmi2_eta_en.json"
SAMPLE = EXAMPLES / "sampleFTA.json"
#: A legacy tree of AND/OR gates with no link: its headline is the tree walk.
PLAIN = REPO_ROOT / "fta_web" / "tests" / "b2b" / "L01_and_or_basic.json"
STATIC = REPO_ROOT / "fta_web" / "static" / "js"

API_KEY = "sk-testkeyDONOTLEAK0123456789abcdefAB12"
PROVIDER_NAME = "OpenAI"


# --------------------------------------------------------------------------
# fixtures and helpers
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def credentials_home(tmp_path, monkeypatch):
    directory = tmp_path / "fta_editor_home"
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_DIR", directory)
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_FILE", directory / "ai_credentials.json")


@pytest.fixture(autouse=True)
def fresh_headline_cache():
    """``engine.diagram_headline`` remembers one document; a test must not
    read another test's."""
    cache = getattr(engine, "_headline_cache", None)
    if cache is not None:
        cache[:] = []
    yield
    if cache is not None:
        cache[:] = []


@pytest.fixture
def app():
    flask = pytest.importorskip("flask")
    from fta_web.routes.ai import ai_bp
    from fta_web.routes.analysis import analysis_bp
    from fta_web.routes.render import render_bp
    from fta_web.routes.tree import tree_bp

    reset_state()
    ai_bridge.reset_handler()
    built = flask.Flask(__name__)
    for blueprint in (tree_bp, ai_bp, render_bp, analysis_bp):
        built.register_blueprint(blueprint)
    built.config.update(TESTING=True)
    return built


@pytest.fixture
def client(app):
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def provider():
    instance = AIProviderFactory.get_provider(PROVIDER_NAME)
    assert instance is not None
    return instance


@pytest.fixture
def configured(client, provider, monkeypatch):
    monkeypatch.setattr(provider, "test_connection", lambda *a, **k: (True, "ok"))
    response = client.post("/api/ai/credentials", json={
        "provider": PROVIDER_NAME, "apiKey": API_KEY,
        "endpoint": "https://api.openai.com/v1", "model": "gpt-4o",
    })
    assert response.status_code == 200, body(response)
    return client


def body(response):
    return json.loads(response.get_data(as_text=True))


def node(node_id, children=None, **kwargs):
    out = {
        "id": node_id,
        "name": kwargs.pop("name", node_id.upper()),
        "type": kwargs.pop("type", "Event"),
        "probability": kwargs.pop("probability", 0.1),
        "logicGate": kwargs.pop("logicGate", ""),
        "notes": "",
        "children": children or [],
        "links": kwargs.pop("links", []),
    }
    out.update(kwargs)
    return out


def link(target, relation="OR"):
    return {"target_id": target, "relation": relation}


def small_tree():
    """root(OR): a, b, g(AND: c, d). ``a`` already links to ``c`` (OR)."""
    return node("root", type="Root", logicGate="OR", probability=1.0, children=[
        node("a", probability=0.1, links=[link("c")]),
        node("b", probability=0.2),
        node("g", type="Gate", logicGate="AND", probability=1.0, children=[
            node("c", probability=0.3),
            node("d", probability=0.4),
        ]),
    ])


def install(tree, mode="FTA"):
    """Make ``tree`` the open document (calculated, clean, no history)."""
    state = get_state()
    with state.lock:
        state.core.set_data(copy.deepcopy(tree))
        state.core.mode = mode
        state.core.recalculate_probabilities()
        state.mark_saved()
    return state


def open_file(path):
    state = get_state()
    with state.lock:
        ok, error = state.core.load_from_json(str(path))
        assert ok, error
        state.core.recalculate_probabilities()
        state.mark_saved()
    return state


def propose(*changes):
    """Queue proposals as the handler would after a reply; their indices."""
    handler = ai_bridge.get_handler()
    start = len(handler.pending_changes)
    handler.pending_changes.extend(changes)
    return list(range(start, start + len(changes)))


def edit(target, **data):
    return AIProposedChange("edit", target, "edit %s" % target, data)


def add(parent, **data):
    return AIProposedChange("add", parent, "add %s" % data.get("id"), data)


def apply(client, indices):
    return client.post("/api/ai/changes/apply", json={"indices": indices})


def find(tree, node_id):
    stack = [tree]
    while stack:
        current = stack.pop()
        if current.get("id") == node_id:
            return current
        stack.extend(current.get("children") or [])
    return None


def links_of(client, node_id):
    return find(body(client.get("/api/state"))["tree"], node_id)["links"]


def core_of(path):
    core = WebCore()
    ok, error = core.load_from_json(str(path))
    assert ok, error
    core.recalculate_probabilities()
    return core


def simple_core(tree, mode="FTA"):
    core = WebCore()
    core.set_data(copy.deepcopy(tree))
    core.mode = mode
    core.recalculate_probabilities()
    return core
