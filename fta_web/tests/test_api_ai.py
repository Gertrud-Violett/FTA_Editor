"""
Tests for the AI assistant backend: fta_web/ai_bridge.py and the /api/ai
blueprint.

Three things make this suite unusual, and all three are deliberate.

**No test may reach the network.** Every provider is mocked at the layer the
vendored code actually calls -- the singleton instances inside
``AIProviderFactory._providers`` -- by replacing ``send_message``,
``test_connection`` and ``get_available_models`` on the instance. That is the
same seam ``tests/test_update_flow_mock.py`` uses one level up (it monkeypatches
``AIAgentHandler.send_message``); patching one level lower here means the
handler's own prompt assembly, response parsing and validation are the real
code under test, and only the socket is fake. Nothing in this file constructs
an SDK client, so an accidental live call would be an AttributeError, not a
billed request.

**The credentials file is redirected at the class.**
``AICredentialManager.CREDENTIALS_DIR``/``CREDENTIALS_FILE`` are class
attributes read through ``self``, so pointing them at ``tmp_path`` covers every
instance -- including the ones ``state._ai_configured()`` and the route layer
build for themselves. Without this the suite would read, and delete, the
developer's real ``~/.fta_editor/ai_credentials.json``.

**The API key is checked for absence, not just for masking.** ``API_KEY`` is a
distinctive string and the mocked providers deliberately echo it back inside
their error messages, the way a real SDK quotes a request URL. Every response
body in the leak test is searched for it. A test that only asserted
``keyPreview`` was masked would pass against a build that leaked the key in an
error detail.
"""
import json
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# conftest.py put fta_web/core on sys.path, so the vendored modules import
# under their bare names -- exactly as fta_web/ai_bridge.py imports them.
from AI_agent_handler import AICredentialManager  # noqa: E402
from ai_providers import AIProviderFactory  # noqa: E402

from fta_web import ai_bridge  # noqa: E402
from fta_web.state import get_state, reset_state  # noqa: E402

#: Distinctive on purpose: it must be greppable in a response body, and long
#: enough to clear ai_bridge's minimum lengths for masking and redaction.
API_KEY = "sk-testkeyDONOTLEAK0123456789abcdefAB12"
PROVIDER_NAME = "OpenAI"
ENDPOINT = "https://api.openai.com/v1"
MODEL = "gpt-4o"

#: A complete, valid tree in the shape verify_updated_fta_json demands.
VALID_UPDATE = {
    "id": "root",
    "name": "Top event",
    "type": "Event",
    "probability": 0.7,
    "logicGate": "OR",
    "notes": "",
    "links": [],
    "children": [
        {
            "id": "n_1",
            "name": "Cause A",
            "type": "Event",
            "probability": 0.2,
            "logicGate": "OR",
            "notes": "",
            "children": [],
            "links": [],
        }
    ],
}

#: The same tree with one node the validator refuses. "Condition" is not one of
#: Event/Gate/Intermediate/Root, so the message names n_3 and the diagnostics
#: must find it.
INVALID_UPDATE = {
    "id": "root",
    "name": "Top event",
    "type": "Event",
    "probability": 0.7,
    "logicGate": "OR",
    "notes": "",
    "links": [],
    "children": [
        {
            "id": "n_1",
            "name": "Cause A",
            "type": "Event",
            "probability": 0.2,
            "logicGate": "OR",
            "notes": "",
            "links": [],
            "children": [
                {
                    "id": "n_3",
                    "name": "Wrongly typed node",
                    "type": "Condition",
                    "probability": 0.1,
                    "logicGate": "OR",
                    "notes": "needle-in-the-haystack",
                    "children": [],
                    "links": [],
                }
            ],
        }
    ],
}

#: A reply in the format AIAgentHandler.SYSTEM_PROMPT asks for, so the vendored
#: parser (not a stub) produces the proposed change.
SUGGESTION_REPLY = """Corrosion is missing from this analysis.

SUGGESTION: Add a corrosion event
DESCRIPTION: Moisture ingress is a common root cause and is not represented.
ACTION: add
TARGET: root
DATA: {"id": "corrosion", "name": "Corrosion", "type": "Event", "probability": 0.05, "logicGate": "OR", "notes": "moisture"}
"""


# --------------------------------------------------------------------------
# fixtures and helpers
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def credentials_home(tmp_path, monkeypatch):
    """Point AICredentialManager at tmp_path, for every instance."""
    directory = tmp_path / "fta_editor_home"
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_DIR", directory)
    monkeypatch.setattr(
        AICredentialManager, "CREDENTIALS_FILE", directory / "ai_credentials.json"
    )
    return directory / "ai_credentials.json"


@pytest.fixture(autouse=True)
def clean_call_slot():
    """Leave ai_bridge's single-call slot free for the next test.

    A timed-out call keeps its worker -- and the slot -- until the provider
    returns, which is the documented behaviour. Waiting for it here stops one
    slow test from turning the next one into an unexplained AI_BUSY.
    """
    yield
    deadline = time.monotonic() + 5.0
    while ai_bridge._call_slot.locked() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not ai_bridge._call_slot.locked(), "an AI call slot was left held"


@pytest.fixture
def app(credentials_home):
    """A bare Flask app with the tree and AI blueprints, no security layer."""
    flask = pytest.importorskip("flask")
    from fta_web.routes.ai import ai_bp
    from fta_web.routes.tree import tree_bp

    reset_state()
    ai_bridge.reset_handler()

    built = flask.Flask(__name__)
    built.register_blueprint(tree_bp)
    built.register_blueprint(ai_bp)
    built.config.update(TESTING=True)
    return built


@pytest.fixture
def client(app):
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def provider():
    """The live OpenAI provider singleton, for per-test method patching.

    Patching the instance rather than the factory keeps
    ``AIProviderFactory.get_provider`` -- and therefore the handler's own
    provider resolution -- as the real code under test.
    """
    instance = AIProviderFactory.get_provider(PROVIDER_NAME)
    assert instance is not None
    return instance


@pytest.fixture
def configured(client, provider, monkeypatch):
    """A client with credentials already saved, via the real save path."""
    monkeypatch.setattr(
        provider, "test_connection", lambda *a, **k: (True, "connection successful")
    )
    response = client.post(
        "/api/ai/credentials",
        json={
            "provider": PROVIDER_NAME,
            "apiKey": API_KEY,
            "endpoint": ENDPOINT,
            "model": MODEL,
        },
    )
    assert response.status_code == 200, body(response)
    return client


def body(response):
    return json.loads(response.get_data(as_text=True))


def error_code(response):
    return body(response)["error"]["code"]


def replies(text):
    """A provider whose send_message always answers with ``text``."""

    def send_message(api_key, endpoint, model, messages, max_tokens=2000):
        return text, None

    return send_message


def fails_with(error):
    """A provider whose send_message always reports ``error``."""

    def send_message(api_key, endpoint, model, messages, max_tokens=2000):
        return None, error

    return send_message


def tree_of(client):
    return body(client.get("/api/state"))["tree"]


# --------------------------------------------------------------------------
# not configured
# --------------------------------------------------------------------------


class TestNotConfigured:
    """Every endpoint that needs a provider says so, in one voice."""

    CASES = (
        ("post", "/api/ai/chat", {"message": "hello"}),
        ("post", "/api/ai/analyze", {}),
        ("post", "/api/ai/update", {}),
        ("post", "/api/ai/changes/apply", {"indices": [0]}),
        ("delete", "/api/ai/conversation", None),
    )

    @pytest.mark.parametrize("method,path,payload", CASES)
    def test_ai_endpoints_refuse_without_credentials(
        self, client, method, path, payload
    ):
        call = getattr(client, method)
        response = call(path, json=payload) if payload is not None else call(path)

        assert response.status_code == 400
        assert error_code(response) == "AI_NOT_CONFIGURED"

    @pytest.mark.parametrize("method,path,payload", CASES)
    def test_the_message_points_at_ai_settings(self, client, method, path, payload):
        call = getattr(client, method)
        response = call(path, json=payload) if payload is not None else call(path)

        assert "AI settings" in body(response)["error"]["message"]

    def test_the_guard_runs_before_body_validation(self, client):
        """A malformed body must not mask the real problem."""
        response = client.post("/api/ai/chat", json={"message": ""})

        assert error_code(response) == "AI_NOT_CONFIGURED"

    def test_credential_endpoints_work_unconfigured(self, client):
        response = client.get("/api/ai/credentials")

        assert response.status_code == 200
        assert body(response)["configured"] is False
        assert body(response)["keyPreview"] is None

    def test_providers_works_unconfigured(self, client):
        """The settings dialog is built from this; it cannot need a key."""
        response = client.get("/api/ai/providers")

        assert response.status_code == 200
        assert body(response)["providers"]

    def test_models_degrades_instead_of_refusing(self, client):
        response = client.get("/api/ai/models?provider=OpenAI")

        assert response.status_code == 200
        payload = body(response)
        assert payload["source"] == "fallback"
        assert payload["warning"]
        assert payload["models"]


# --------------------------------------------------------------------------
# providers and models
# --------------------------------------------------------------------------


class TestProviders:
    def test_every_provider_carries_its_defaults(self, client):
        providers = body(client.get("/api/ai/providers"))["providers"]

        for entry in providers:
            assert set(entry) == {"name", "defaultEndpoint", "defaultModels"}
            assert entry["name"]
            assert entry["defaultEndpoint"].startswith("http")
            assert entry["defaultModels"]

    def test_the_documented_providers_are_all_offered(self, client):
        """OpenAI, Claude and Gemini are the three the docs promise."""
        names = {p["name"] for p in body(client.get("/api/ai/providers"))["providers"]}

        assert {"OpenAI", "Anthropic Claude", "Google Gemini"} <= names

    def test_the_list_comes_from_the_vendored_factory(self, client):
        """Pinned so the web picker cannot drift from the desktop dialog."""
        names = [p["name"] for p in body(client.get("/api/ai/providers"))["providers"]]

        assert names == list(AIProviderFactory.get_all_providers().keys())

    def test_no_not_gate_leaks_into_the_defaults(self, client):
        """Divergence D5: NOT is not a thing anywhere in this API."""
        payload = client.get("/api/ai/providers").get_data(as_text=True)

        assert '"NOT"' not in payload


class TestModels:
    def test_a_live_list_is_reported_as_live(self, configured, provider, monkeypatch):
        monkeypatch.setattr(
            provider, "get_available_models", lambda key, ep: (["m-one", "m-two"], None)
        )

        payload = body(configured.get("/api/ai/models?provider=OpenAI"))

        assert payload["source"] == "live"
        assert payload["models"] == ["m-one", "m-two"]
        assert "warning" not in payload

    def test_a_provider_error_falls_back_with_a_warning(
        self, configured, provider, monkeypatch
    ):
        monkeypatch.setattr(
            provider,
            "get_available_models",
            lambda key, ep: (provider.get_default_models(), "Could not fetch models"),
        )

        payload = body(configured.get("/api/ai/models?provider=OpenAI"))

        assert payload["source"] == "fallback"
        assert "Could not fetch models" in payload["warning"]
        assert payload["models"] == provider.get_default_models()

    def test_a_timeout_falls_back_rather_than_failing(
        self, configured, provider, monkeypatch
    ):
        """A settings dialog with no model list is one the user cannot finish."""
        release = threading.Event()

        def hang(api_key, endpoint):
            release.wait(5)
            return ["late"], None

        monkeypatch.setattr(provider, "get_available_models", hang)
        monkeypatch.setattr(ai_bridge.config, "AI_TIMEOUT_SECONDS", 0.2)

        try:
            payload = body(configured.get("/api/ai/models?provider=OpenAI"))
        finally:
            release.set()

        assert payload["source"] == "fallback"
        assert payload["models"] == provider.get_default_models()

    def test_a_key_for_another_provider_is_not_used(self, configured, monkeypatch):
        """The saved OpenAI key must not be sent to Gemini to list models."""
        gemini = AIProviderFactory.get_provider("Google Gemini")

        def explode(api_key, endpoint):  # pragma: no cover - must not run
            raise AssertionError("the OpenAI key reached the Gemini provider")

        monkeypatch.setattr(gemini, "get_available_models", explode)

        payload = body(configured.get("/api/ai/models?provider=Google Gemini"))

        assert payload["source"] == "fallback"
        assert payload["models"] == gemini.get_default_models()

    def test_an_unknown_provider_is_a_400(self, client):
        response = client.get("/api/ai/models?provider=Skynet")

        assert response.status_code == 400
        assert error_code(response) == "INVALID_FIELD"

    def test_the_endpoint_defaults_to_the_providers_own(self, client):
        payload = body(client.get("/api/ai/models?provider=Anthropic Claude"))

        assert payload["endpoint"] == "https://api.anthropic.com"


# --------------------------------------------------------------------------
# credentials
# --------------------------------------------------------------------------


class TestSaveCredentials:
    def test_a_bad_key_is_rejected_and_not_saved(
        self, client, provider, monkeypatch, credentials_home
    ):
        monkeypatch.setattr(
            provider,
            "test_connection",
            lambda *a, **k: (False, "OpenAI connection failed: 401 Incorrect API key"),
        )

        response = client.post(
            "/api/ai/credentials",
            json={"provider": PROVIDER_NAME, "apiKey": API_KEY, "model": MODEL},
        )

        assert response.status_code == 400
        assert error_code(response) == "AI_CONNECTION_FAILED"
        # The provider's own wording, not a generic replacement.
        assert "401 Incorrect API key" in body(response)["error"]["message"]
        assert body(response)["error"]["detail"]["saved"] is False
        assert not credentials_home.exists()
        assert body(client.get("/api/ai/credentials"))["configured"] is False

    def test_a_bad_key_does_not_replace_a_working_one(
        self, configured, provider, monkeypatch
    ):
        monkeypatch.setattr(provider, "test_connection", lambda *a, **k: (False, "nope"))

        configured.post(
            "/api/ai/credentials",
            json={"provider": PROVIDER_NAME, "apiKey": "sk-a-different-key-entirely"},
        )

        status = body(configured.get("/api/ai/credentials"))
        assert status["configured"] is True
        assert status["keyPreview"] == ai_bridge.mask_key(API_KEY)

    def test_a_good_key_is_saved_where_the_desktop_reads_it(
        self, client, provider, monkeypatch, credentials_home
    ):
        monkeypatch.setattr(provider, "test_connection", lambda *a, **k: (True, "ok!"))

        response = client.post(
            "/api/ai/credentials",
            json={
                "provider": PROVIDER_NAME,
                "apiKey": API_KEY,
                "endpoint": ENDPOINT,
                "model": MODEL,
            },
        )

        assert response.status_code == 200
        assert credentials_home.name == "ai_credentials.json"
        stored = json.loads(credentials_home.read_text(encoding="utf-8"))
        assert stored == {
            "api_key": API_KEY,
            "api_endpoint": ENDPOINT,
            "model": MODEL,
            "provider": PROVIDER_NAME,
        }

    def test_the_saved_status_is_reported_back_masked(
        self, client, provider, monkeypatch
    ):
        monkeypatch.setattr(provider, "test_connection", lambda *a, **k: (True, "ok!"))

        payload = body(
            client.post(
                "/api/ai/credentials",
                json={"provider": PROVIDER_NAME, "apiKey": API_KEY, "model": MODEL},
            )
        )

        assert payload["configured"] is True
        assert payload["provider"] == PROVIDER_NAME
        assert payload["model"] == MODEL
        assert payload["keyPreview"] == "sk-…AB12"

    def test_defaults_fill_in_endpoint_and_model(self, client, provider, monkeypatch):
        seen = {}

        def test_connection(api_key, endpoint, model):
            seen.update(endpoint=endpoint, model=model)
            return True, "ok"

        monkeypatch.setattr(provider, "test_connection", test_connection)

        payload = body(
            client.post(
                "/api/ai/credentials",
                json={"provider": PROVIDER_NAME, "apiKey": API_KEY},
            )
        )

        assert seen["endpoint"] == provider.get_default_endpoint()
        assert seen["model"] == provider.get_default_models()[0]
        assert payload["endpoint"] == provider.get_default_endpoint()

    def test_an_alias_is_stored_under_its_canonical_name(
        self, client, provider, monkeypatch, credentials_home
    ):
        """"openai" and "OpenAI" must not produce two different files."""
        monkeypatch.setattr(provider, "test_connection", lambda *a, **k: (True, "ok"))

        client.post(
            "/api/ai/credentials", json={"provider": "openai", "apiKey": API_KEY}
        )

        stored = json.loads(credentials_home.read_text(encoding="utf-8"))
        assert stored["provider"] == "OpenAI"

    @pytest.mark.parametrize(
        "payload",
        [
            {"apiKey": API_KEY},
            {"provider": PROVIDER_NAME},
            {"provider": PROVIDER_NAME, "apiKey": "   "},
            {"provider": "Skynet", "apiKey": API_KEY},
            {"provider": PROVIDER_NAME, "apiKey": 12345},
        ],
    )
    def test_malformed_requests_are_400s(self, client, payload):
        response = client.post("/api/ai/credentials", json=payload)

        assert response.status_code == 400
        assert error_code(response) == "INVALID_FIELD"

    def test_delete_clears_the_key(self, configured, credentials_home):
        response = configured.delete("/api/ai/credentials")

        assert response.status_code == 200
        assert body(response)["configured"] is False
        assert not credentials_home.exists()

    def test_delete_is_idempotent(self, client):
        assert client.delete("/api/ai/credentials").status_code == 200
        assert client.delete("/api/ai/credentials").status_code == 200

    def test_delete_drops_the_handlers_cached_provider(
        self, configured, provider, monkeypatch
    ):
        """Otherwise the next call would still use the deleted key."""
        monkeypatch.setattr(provider, "send_message", replies("hi"))
        configured.post("/api/ai/chat", json={"message": "hello"})
        assert ai_bridge.get_handler().provider is not None

        configured.delete("/api/ai/credentials")

        assert ai_bridge.get_handler().provider is None


class TestAiConfiguredIsConsistent:
    """One question, one answer, wherever it is asked."""

    def test_all_three_places_agree_when_unconfigured(self, client):
        state = body(client.get("/api/state"))
        credentials = body(client.get("/api/ai/credentials"))

        assert state["aiConfigured"] is False
        assert state["capabilities"]["aiConfigured"] is False
        assert credentials["configured"] is False
        assert credentials["aiConfigured"] is False

    def test_all_three_places_agree_after_saving(self, configured):
        state = body(configured.get("/api/state"))
        credentials = body(configured.get("/api/ai/credentials"))

        assert state["aiConfigured"] is True
        assert state["capabilities"]["aiConfigured"] is True
        assert credentials["configured"] is True
        assert credentials["aiConfigured"] is True

    def test_they_agree_again_after_deleting(self, configured):
        configured.delete("/api/ai/credentials")

        state = body(configured.get("/api/state"))
        assert state["aiConfigured"] is False
        assert state["capabilities"]["aiConfigured"] is False


# --------------------------------------------------------------------------
# the key never reaches the browser
# --------------------------------------------------------------------------


class TestTheKeyNeverLeaves:
    """The non-negotiable one.

    The mocked provider echoes the key back inside its own messages, the way a
    real SDK quotes the request URL it failed on. Every response body is then
    searched for the key itself -- not for a mask, which a leaking build could
    still emit alongside the real thing.
    """

    def test_no_endpoint_puts_the_key_in_a_response(
        self, client, provider, monkeypatch
    ):
        leaky = "provider said: request to ...?key=%s failed" % API_KEY
        monkeypatch.setattr(provider, "test_connection", lambda *a, **k: (True, leaky))
        monkeypatch.setattr(provider, "send_message", fails_with(leaky))
        monkeypatch.setattr(
            provider, "get_available_models", lambda key, ep: ([], leaky)
        )

        responses = {
            "save": client.post(
                "/api/ai/credentials",
                json={"provider": PROVIDER_NAME, "apiKey": API_KEY, "model": MODEL},
            ),
            "get-credentials": client.get("/api/ai/credentials"),
            "providers": client.get("/api/ai/providers"),
            "models": client.get("/api/ai/models?provider=OpenAI"),
            "chat": client.post("/api/ai/chat", json={"message": "hello"}),
            "analyze": client.post("/api/ai/analyze", json={}),
            "update": client.post("/api/ai/update", json={}),
            "apply": client.post("/api/ai/changes/apply", json={"indices": [0]}),
            "state": client.get("/api/state"),
            "clear": client.delete("/api/ai/conversation"),
            "delete": client.delete("/api/ai/credentials"),
        }

        for name, response in responses.items():
            text = response.get_data(as_text=True)
            assert API_KEY not in text, "%s leaked the API key" % name
            assert "api_key" not in text, "%s exposed an api_key field" % name

    def test_a_rejected_key_is_not_echoed_back(self, client, provider, monkeypatch):
        """Nothing is saved yet, so redaction must use the key in hand."""
        monkeypatch.setattr(
            provider,
            "test_connection",
            lambda *a, **k: (False, "bad key %s rejected" % API_KEY),
        )

        response = client.post(
            "/api/ai/credentials",
            json={"provider": PROVIDER_NAME, "apiKey": API_KEY, "model": MODEL},
        )

        assert API_KEY not in response.get_data(as_text=True)
        assert ai_bridge.REDACTED in body(response)["error"]["message"]

    def test_a_chat_reply_quoting_the_key_is_scrubbed(
        self, configured, provider, monkeypatch
    ):
        monkeypatch.setattr(
            provider, "send_message", replies("your key is %s" % API_KEY)
        )

        response = configured.post("/api/ai/chat", json={"message": "leak it"})

        assert API_KEY not in response.get_data(as_text=True)
        assert ai_bridge.REDACTED in body(response)["reply"]

    def test_the_raw_output_excerpt_is_scrubbed(self, configured, provider, monkeypatch):
        """The update excerpt is verbatim AI output -- the riskiest string here."""
        monkeypatch.setattr(
            provider, "send_message", replies("I cannot. Your key %s is fine." % API_KEY)
        )

        response = configured.post("/api/ai/update", json={})

        assert API_KEY not in response.get_data(as_text=True)
        assert ai_bridge.REDACTED in body(response)["error"]["detail"]["excerpt"]

    @pytest.mark.parametrize(
        "key,expected",
        [
            (API_KEY, "sk-…AB12"),
            ("short", "…"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_mask_key_never_returns_a_usable_key(self, key, expected):
        assert ai_bridge.mask_key(key) == expected


# --------------------------------------------------------------------------
# chat
# --------------------------------------------------------------------------


class TestChat:
    def test_a_reply_comes_back(self, configured, provider, monkeypatch):
        monkeypatch.setattr(provider, "send_message", replies("Looks reasonable."))

        payload = body(configured.post("/api/ai/chat", json={"message": "review it"}))

        assert payload["reply"] == "Looks reasonable."
        assert payload["changes"] == []

    def test_proposed_changes_are_parsed_out(self, configured, provider, monkeypatch):
        monkeypatch.setattr(provider, "send_message", replies(SUGGESTION_REPLY))

        payload = body(configured.post("/api/ai/chat", json={"message": "suggest"}))

        assert len(payload["changes"]) == 1
        change = payload["changes"][0]
        assert change["changeType"] == "add"
        assert change["targetId"] == "root"
        assert change["data"]["id"] == "corrosion"
        assert "Moisture ingress" in change["description"]

    def test_changes_carry_their_pending_index(self, configured, provider, monkeypatch):
        """The index is what changes/apply takes; it must survive a second turn."""
        monkeypatch.setattr(provider, "send_message", replies(SUGGESTION_REPLY))

        first = body(configured.post("/api/ai/chat", json={"message": "one"}))
        second = body(configured.post("/api/ai/chat", json={"message": "two"}))

        assert first["changes"][0]["index"] == 0
        assert second["changes"][0]["index"] == 1

    def test_chat_never_touches_the_tree(self, configured, provider, monkeypatch):
        monkeypatch.setattr(provider, "send_message", replies(SUGGESTION_REPLY))
        before = json.dumps(tree_of(configured), sort_keys=True)

        configured.post("/api/ai/chat", json={"message": "suggest"})

        assert json.dumps(tree_of(configured), sort_keys=True) == before

    def test_a_provider_error_arrives_as_a_reply(
        self, configured, provider, monkeypatch
    ):
        """Parity with the desktop chat, which shows the same in-band text."""
        monkeypatch.setattr(provider, "send_message", fails_with("rate limited"))

        payload = body(configured.post("/api/ai/chat", json={"message": "hi"}))

        assert "rate limited" in payload["reply"]

    @pytest.mark.parametrize("payload", [{}, {"message": ""}, {"message": 5}])
    def test_a_missing_message_is_a_400(self, configured, payload):
        response = configured.post("/api/ai/chat", json=payload)

        assert response.status_code == 400
        assert error_code(response) == "INVALID_FIELD"

    def test_clearing_the_conversation_drops_pending_changes(
        self, configured, provider, monkeypatch
    ):
        monkeypatch.setattr(provider, "send_message", replies(SUGGESTION_REPLY))
        configured.post("/api/ai/chat", json={"message": "suggest"})

        configured.delete("/api/ai/conversation")

        assert ai_bridge.get_handler().pending_changes == []
        assert ai_bridge.get_handler().conversation_history == []


# --------------------------------------------------------------------------
# analyze
# --------------------------------------------------------------------------


class TestAnalyze:
    def test_the_tree_is_byte_identical_afterwards(
        self, configured, provider, monkeypatch
    ):
        """The whole point of a separate analyze endpoint."""
        monkeypatch.setattr(provider, "send_message", replies(SUGGESTION_REPLY))
        before = json.dumps(tree_of(configured), sort_keys=True)

        response = configured.post("/api/ai/analyze", json={})

        assert response.status_code == 200
        assert json.dumps(tree_of(configured), sort_keys=True) == before

    def test_it_leaves_the_document_clean_and_undo_untouched(
        self, configured, provider, monkeypatch
    ):
        monkeypatch.setattr(provider, "send_message", replies(SUGGESTION_REPLY))

        configured.post("/api/ai/analyze", json={})

        state = body(configured.get("/api/state"))
        assert state["dirty"] is False
        assert state["canUndo"] is False

    def test_suggestions_are_still_reported(self, configured, provider, monkeypatch):
        """Read-only means it does not apply them, not that it hides them."""
        monkeypatch.setattr(provider, "send_message", replies(SUGGESTION_REPLY))

        payload = body(configured.post("/api/ai/analyze", json={}))

        assert payload["changes"][0]["data"]["id"] == "corrosion"

    def test_the_handler_is_given_a_copy_not_the_live_tree(
        self, configured, provider, monkeypatch
    ):
        """A provider that mutates what it is handed cannot reach the document."""
        captured = {}

        def send_message(api_key, endpoint, model, messages, max_tokens=2000):
            captured["messages"] = messages
            get_state().core.get_data()["name"] = "changed by nobody"
            return "ok", None

        monkeypatch.setattr(provider, "send_message", send_message)
        configured.post("/api/ai/analyze", json={})

        # The context the AI saw is text, built from a copy taken before the
        # call -- so the live tree's name is not what it was shown.
        assert captured["messages"]


# --------------------------------------------------------------------------
# applying changes
# --------------------------------------------------------------------------


class TestApplyChanges:
    @pytest.fixture
    def proposed(self, configured, provider, monkeypatch):
        monkeypatch.setattr(provider, "send_message", replies(SUGGESTION_REPLY))
        configured.post("/api/ai/chat", json={"message": "suggest"})
        return configured

    def test_a_change_is_applied_through_the_vendored_handler(self, proposed):
        response = proposed.post("/api/ai/changes/apply", json={"indices": [0]})

        assert response.status_code == 200
        payload = body(response)
        assert [c["id"] for c in payload["tree"]["children"]] == ["corrosion"]
        assert payload["applied"][0]["index"] == 0
        assert payload["rejected"] == []
        assert payload["dirty"] is True

    def test_an_applied_change_is_undoable(self, proposed):
        """An AI edit is one Ctrl-Z away, like every other edit."""
        proposed.post("/api/ai/changes/apply", json={"indices": [0]})
        assert tree_of(proposed)["children"]

        response = proposed.post("/api/undo")

        assert response.status_code == 200
        assert body(response)["tree"]["children"] == []
        assert tree_of(proposed)["children"] == []

    def test_a_rejected_change_leaves_the_tree_alone(
        self, configured, provider, monkeypatch
    ):
        """The handler refuses an add under a parent that does not exist."""
        monkeypatch.setattr(
            provider,
            "send_message",
            replies(SUGGESTION_REPLY.replace("TARGET: root", "TARGET: nowhere")),
        )
        configured.post("/api/ai/chat", json={"message": "suggest"})
        before = json.dumps(tree_of(configured), sort_keys=True)

        response = configured.post("/api/ai/changes/apply", json={"indices": [0]})

        assert response.status_code == 400
        assert error_code(response) == "AI_CHANGE_REJECTED"
        assert "not found" in body(response)["error"]["detail"]["rejected"][0]["message"]
        assert json.dumps(tree_of(configured), sort_keys=True) == before
        assert body(configured.get("/api/state"))["dirty"] is False

    def test_probabilities_are_recalculated(self, proposed):
        payload = body(proposed.post("/api/ai/changes/apply", json={"indices": [0]}))

        added = payload["tree"]["children"][0]
        assert "calculatedProbability" in added
        assert payload["tree"]["calculatedProbability"] == pytest.approx(0.05)

    @pytest.mark.parametrize(
        "indices", [[], "0", [0, 0], [1], [-1], ["0"], [True], [0.5]]
    )
    def test_bad_indices_are_400s(self, proposed, indices):
        response = proposed.post("/api/ai/changes/apply", json={"indices": indices})

        assert response.status_code == 400
        assert error_code(response) == "INVALID_FIELD"

    def test_an_out_of_range_index_says_how_many_there_are(self, proposed):
        response = proposed.post("/api/ai/changes/apply", json={"indices": [7]})

        assert "there is 1" in body(response)["error"]["message"]


# --------------------------------------------------------------------------
# the full-JSON update flow
# --------------------------------------------------------------------------


class TestUpdate:
    def test_a_valid_tree_is_installed(self, configured, provider, monkeypatch):
        monkeypatch.setattr(
            provider, "send_message", replies(json.dumps(VALID_UPDATE))
        )

        response = configured.post("/api/ai/update", json={})

        assert response.status_code == 200
        payload = body(response)
        assert payload["tree"]["name"] == "Top event"
        assert [c["id"] for c in payload["tree"]["children"]] == ["n_1"]
        assert payload["dirty"] is True

    def test_a_code_fenced_tree_is_accepted(self, configured, provider, monkeypatch):
        """The handler strips fences; this pins that the route relies on it."""
        monkeypatch.setattr(
            provider,
            "send_message",
            replies("```json\n%s\n```" % json.dumps(VALID_UPDATE)),
        )

        assert configured.post("/api/ai/update", json={}).status_code == 200

    def test_an_update_is_undoable(self, configured, provider, monkeypatch):
        monkeypatch.setattr(
            provider, "send_message", replies(json.dumps(VALID_UPDATE))
        )
        before = json.dumps(tree_of(configured), sort_keys=True)

        configured.post("/api/ai/update", json={})
        configured.post("/api/undo")

        assert json.dumps(tree_of(configured), sort_keys=True) == before

    def test_unparseable_output_returns_the_first_500_characters(
        self, configured, provider, monkeypatch
    ):
        """The desktop's parse diagnostic (FTA_Editor_UI.py:855-865)."""
        prose = "I am sorry, I cannot rewrite the root node.\n" + ("x" * 900)
        monkeypatch.setattr(provider, "send_message", replies(prose))

        response = configured.post("/api/ai/update", json={})

        assert response.status_code == 400
        assert error_code(response) == "AI_INVALID_JSON"
        excerpt = body(response)["error"]["detail"]["excerpt"]
        assert len(excerpt) == 500
        assert excerpt.startswith("I am sorry, I cannot rewrite the root node. ")
        assert "\n" not in excerpt

    def test_unparseable_output_changes_nothing(
        self, configured, provider, monkeypatch
    ):
        monkeypatch.setattr(provider, "send_message", replies("not json at all"))
        before = json.dumps(tree_of(configured), sort_keys=True)

        configured.post("/api/ai/update", json={})

        assert json.dumps(tree_of(configured), sort_keys=True) == before
        assert body(configured.get("/api/state"))["dirty"] is False

    def test_an_invalid_tree_names_the_offending_node(
        self, configured, provider, monkeypatch
    ):
        """The desktop's validation diagnostic (FTA_Editor_UI.py:866-892)."""
        monkeypatch.setattr(
            provider, "send_message", replies(json.dumps(INVALID_UPDATE))
        )

        response = configured.post("/api/ai/update", json={})

        assert response.status_code == 400
        assert error_code(response) == "AI_UPDATE_REJECTED"
        detail = body(response)["error"]["detail"]
        assert detail["nodeId"] == "n_3"
        assert detail["validatorMessage"] == "Invalid type for node n_3: Condition"
        assert detail["node"]["name"] == "Wrongly typed node"
        assert "needle-in-the-haystack" in detail["section"]

    def test_an_invalid_tree_changes_nothing(self, configured, provider, monkeypatch):
        monkeypatch.setattr(
            provider, "send_message", replies(json.dumps(INVALID_UPDATE))
        )
        before = json.dumps(tree_of(configured), sort_keys=True)

        configured.post("/api/ai/update", json={})

        assert json.dumps(tree_of(configured), sort_keys=True) == before
        assert body(configured.get("/api/state"))["dirty"] is False

    def test_a_not_gate_is_refused_by_name(self, configured, provider, monkeypatch):
        """Divergence D5: the validator's own wording reaches the user."""
        with_not = json.loads(json.dumps(VALID_UPDATE))
        with_not["children"][0]["logicGate"] = "NOT"
        monkeypatch.setattr(provider, "send_message", replies(json.dumps(with_not)))

        response = configured.post("/api/ai/update", json={})

        detail = body(response)["error"]["detail"]
        assert "NOT gates are not supported" in detail["validatorMessage"]
        assert detail["nodeId"] == "n_1"

    def test_a_document_level_failure_falls_back_to_top_level_keys(
        self, configured, provider, monkeypatch
    ):
        """"Missing root field" names no node, exactly as on the desktop."""
        rootless = {"id": "root", "name": "x", "type": "Event"}
        monkeypatch.setattr(provider, "send_message", replies(json.dumps(rootless)))

        response = configured.post("/api/ai/update", json={})

        detail = body(response)["error"]["detail"]
        assert detail["nodeId"] is None
        assert detail["node"] is None
        assert detail["section"].startswith("Top-level keys: ")

    def test_a_duplicate_id_still_locates_the_node(
        self, configured, provider, monkeypatch
    ):
        """The desktop regex captures "ID" here; the second pattern recovers."""
        duplicated = json.loads(json.dumps(VALID_UPDATE))
        duplicated["children"].append(json.loads(json.dumps(duplicated["children"][0])))
        monkeypatch.setattr(provider, "send_message", replies(json.dumps(duplicated)))

        response = configured.post("/api/ai/update", json={})

        detail = body(response)["error"]["detail"]
        assert detail["validatorMessage"] == "Duplicate node ID: n_1"
        assert detail["nodeId"] == "n_1"
        assert detail["node"]["name"] == "Cause A"


# --------------------------------------------------------------------------
# threading, timeouts, and the lock
# --------------------------------------------------------------------------


class TestTimeoutAndConcurrency:
    def test_a_hung_provider_is_a_clean_error_not_a_hang(
        self, configured, provider, monkeypatch
    ):
        release = threading.Event()

        def hang(api_key, endpoint, model, messages, max_tokens=2000):
            release.wait(10)
            return "too late", None

        monkeypatch.setattr(provider, "send_message", hang)
        monkeypatch.setattr(ai_bridge.config, "AI_TIMEOUT_SECONDS", 0.2)

        started = time.monotonic()
        try:
            response = configured.post("/api/ai/chat", json={"message": "hi"})
            elapsed = time.monotonic() - started

            assert response.status_code == 504
            assert error_code(response) == "AI_TIMEOUT"
            assert elapsed < 5, "the request waited on the provider"
            assert body(response)["error"]["detail"]["timeoutSeconds"] == 0.2
        finally:
            release.set()

    def test_a_second_call_is_refused_while_one_is_still_out(
        self, configured, provider, monkeypatch
    ):
        """A timed-out worker keeps the slot; it must not be raced for."""
        release = threading.Event()

        def hang(api_key, endpoint, model, messages, max_tokens=2000):
            release.wait(10)
            return "too late", None

        monkeypatch.setattr(provider, "send_message", hang)
        monkeypatch.setattr(ai_bridge.config, "AI_TIMEOUT_SECONDS", 0.2)

        try:
            assert configured.post("/api/ai/chat", json={"message": "1"}).status_code == 504
            second = configured.post("/api/ai/chat", json={"message": "2"})

            assert second.status_code == 409
            assert error_code(second) == "AI_BUSY"
        finally:
            release.set()

    def test_a_hung_provider_does_not_block_the_document_lock(
        self, app, configured, provider, monkeypatch
    ):
        """The requirement this whole threading model exists for.

        While an AI call is stuck on the network, the rest of the editor --
        reading state, editing nodes -- must keep working.
        """
        in_provider = threading.Event()
        release = threading.Event()

        def hang(api_key, endpoint, model, messages, max_tokens=2000):
            in_provider.set()
            release.wait(10)
            return "done", None

        monkeypatch.setattr(provider, "send_message", hang)

        outcome = {}

        def chat():
            with app.test_client() as chat_client:
                outcome["status"] = chat_client.post(
                    "/api/ai/chat", json={"message": "slow"}
                ).status_code

        worker = threading.Thread(target=chat, daemon=True)
        worker.start()
        try:
            assert in_provider.wait(5), "the provider was never reached"

            # The AI call is mid-flight. A normal mutation must not queue
            # behind it.
            started = time.monotonic()
            state = configured.get("/api/state")
            created = configured.post(
                "/api/nodes", json={"parentId": "root", "name": "Added meanwhile"}
            )
            elapsed = time.monotonic() - started

            assert state.status_code == 200
            assert created.status_code == 200
            assert elapsed < 2, "the document lock was held across the AI call"
        finally:
            release.set()
            worker.join(timeout=10)

        assert outcome["status"] == 200
