"""
Regressions from the October 2026 review of the AI assistant (findings AI-*).

Same rules as ``test_api_ai.py``: no test reaches the network (the provider
singletons inside ``AIProviderFactory`` are patched on the instance, so the
vendored handler's prompt assembly, parsing and change application are the
real code under test), and the credentials file is redirected at the class so
the developer's ``~/.fta_editor`` is never read or written.
"""
import json
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from AI_agent_handler import AICredentialManager  # noqa: E402
from ai_providers import AIProviderFactory  # noqa: E402

from fta_web import ai_bridge  # noqa: E402
from fta_web.state import get_state, reset_state  # noqa: E402

pytest.importorskip("flask")

API_KEY = "sk-testkeyDONOTLEAK0123456789abcdefAB12"
PROVIDER_NAME = "OpenAI"
STATIC = REPO_ROOT / "fta_web" / "static" / "js"


# --------------------------------------------------------------------------
# fixtures and helpers
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def credentials_home(tmp_path, monkeypatch):
    directory = tmp_path / "fta_editor_home"
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_DIR", directory)
    monkeypatch.setattr(
        AICredentialManager, "CREDENTIALS_FILE", directory / "ai_credentials.json"
    )
    return directory / "ai_credentials.json"


@pytest.fixture(autouse=True)
def clean_call_slot():
    yield
    deadline = time.monotonic() + 5.0
    while ai_bridge._call_slot.locked() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not ai_bridge._call_slot.locked(), "an AI call slot was left held"


@pytest.fixture
def app(tmp_path):
    import flask

    from fta_web.routes.ai import ai_bp
    from fta_web.routes.files import files_bp
    from fta_web.routes.tree import tree_bp

    reset_state()
    ai_bridge.reset_handler()
    get_state().fs_root = tmp_path
    built = flask.Flask(__name__)
    for blueprint in (tree_bp, files_bp, ai_bp):
        built.register_blueprint(blueprint)
    built.config.update(TESTING=True)
    return built


@pytest.fixture
def provider():
    return AIProviderFactory.get_provider(PROVIDER_NAME)


@pytest.fixture
def client(app, provider, monkeypatch):
    """A client with credentials saved through the real save path."""
    monkeypatch.setattr(provider, "test_connection", lambda *a, **k: (True, "ok"))
    with app.test_client() as test_client:
        response = test_client.post(
            "/api/ai/credentials", json={"provider": PROVIDER_NAME, "apiKey": API_KEY}
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        yield test_client


def body(response):
    return json.loads(response.get_data(as_text=True))


def error_code(response):
    return body(response)["error"]["code"]


def replies(text):
    def send_message(api_key, endpoint, model, messages, max_tokens=2000):
        return text, None

    return send_message


def add(client, **fields):
    fields.setdefault("name", "Event")
    response = client.post("/api/nodes", json=dict(fields, parentId="root"))
    assert response.status_code == 200, body(response)
    return body(response)["nodeId"]


def children(client):
    return [
        (n["id"], n["name"], n["probability"], n["notes"])
        for n in body(client.get("/api/state"))["tree"]["children"]
    ]


def edit_reply(node_id, name, probability_literal="0.2", notes_literal='""'):
    """A reply in the format SYSTEM_PROMPT asks for: one 'edit' proposal."""
    return (
        "SUGGESTION: Revise %s\nDESCRIPTION: field data says otherwise.\n"
        "ACTION: edit\nTARGET: %s\n"
        'DATA: {"id": "%s", "name": "%s", "probability": %s, "notes": %s}\n'
        % (name, node_id, node_id, name, probability_literal, notes_literal)
    )


def add_reply(probability_literal="0.05", notes_literal='"moisture"'):
    return (
        "SUGGESTION: Add corrosion\nDESCRIPTION: missing root cause.\n"
        "ACTION: add\nTARGET: root\n"
        'DATA: {"id": "corrosion", "name": "Corrosion", "type": "Event", '
        '"probability": %s, "notes": %s}\n' % (probability_literal, notes_literal)
    )


def write_document(path, child_name="Valve stuck", probability=1e-5):
    path.write_text(json.dumps({
        "title": "Plant B", "date": "2026-01-01", "mode": "FTA",
        "tree": {
            "id": "root", "name": "Plant B top", "type": "Root", "probability": 1.0,
            "logicGate": "OR", "notes": "", "links": [],
            "children": [{
                "id": "root_0", "name": child_name, "type": "Event",
                "probability": probability, "logicGate": "OR",
                "notes": "reviewed value", "links": [], "children": [],
            }],
        },
    }), encoding="utf-8")
    return path


def tree_with(*nodes, **root_fields):
    """A complete tree in the shape verify_updated_fta_json demands."""
    root = {
        "id": "root", "name": "RootEvent", "type": "Root", "probability": 1.0,
        "logicGate": "OR", "notes": "", "links": [], "children": [],
    }
    root.update(root_fields)
    for node in nodes:
        full = {"type": "Event", "probability": 0.1, "logicGate": "OR", "notes": "",
                "links": [], "children": []}
        full.update(node)
        root["children"].append(full)
    return root


class Blocked:
    """A provider call that waits, so the test can act while it is out."""

    def __init__(self, text):
        self.text = text
        self.inside = threading.Event()
        self.release = threading.Event()

    def __call__(self, api_key, endpoint, model, messages, max_tokens=2000):
        self.inside.set()
        self.release.wait(10)
        return self.text, None


def in_background(app, method, url, payload=None):
    """Run one request on its own client and thread; returns (thread, outcome)."""
    outcome = {}

    def run():
        with app.test_client() as other:
            outcome["response"] = getattr(other, method)(url, json=payload)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, outcome


# --------------------------------------------------------------------------
# AI-01: an update lands on whatever document is open when the model answers
# --------------------------------------------------------------------------


def _edit_a_node(client, tmp_path, node_id):
    response = client.patch(
        "/api/nodes/%s" % node_id, json={"probability": 0.9, "name": "Edited meanwhile"}
    )
    assert response.status_code == 200


def _add_a_node(client, tmp_path, node_id):
    add(client, name="Added meanwhile", probability=0.3)


def _open_another_file(client, tmp_path, node_id):
    path = write_document(tmp_path / "plant_b.json")
    assert client.post("/api/file/open", json={"path": str(path)}).status_code == 200


def _start_a_new_document(client, tmp_path, node_id):
    assert client.post("/api/new", json={"force": True}).status_code == 200


class TestUpdateIsNotInstalledOverAChangedDocument:
    """The model was shown a snapshot; installing its tree over a document
    that changed since silently undid the user's edits -- and after Open it
    replaced the *other* file's tree, under that file's title and path, so
    the next Save wrote the wrong analysis into it."""

    @pytest.mark.parametrize(
        "meanwhile",
        [_edit_a_node, _add_a_node, _open_another_file, _start_a_new_document],
        ids=["edit", "add", "open", "new"],
    )
    def test_nothing_is_replaced_and_the_user_is_told(
        self, app, client, provider, monkeypatch, tmp_path, meanwhile
    ):
        pump = add(client, name="Pump fails", probability=0.1)
        rewritten = tree_with(
            {"id": pump, "name": "Pump fails", "probability": 0.1},
            {"id": "ai_new", "name": "Added by AI", "probability": 0.01},
        )
        blocked = Blocked(json.dumps(rewritten))
        monkeypatch.setattr(provider, "send_message", blocked)

        thread, outcome = in_background(app, "post", "/api/ai/update", {})
        try:
            assert blocked.inside.wait(5), "the provider was never reached"
            meanwhile(client, tmp_path, pump)
            before = body(client.get("/api/state"))
        finally:
            blocked.release.set()
            thread.join(10)

        response = outcome["response"]
        assert response.status_code == 409, body(response)
        assert error_code(response) == "AI_DOCUMENT_CHANGED"
        after = body(client.get("/api/state"))
        assert after["tree"] == before["tree"]
        assert after["canUndo"] == before["canUndo"]
        assert after["dirty"] == before["dirty"]
        assert "ai_new" not in json.dumps(after["tree"])

    def test_an_edit_that_was_undone_again_does_not_block_the_update(
        self, app, client, provider, monkeypatch
    ):
        """Equal content is the same document: no false alarm."""
        pump = add(client, name="Pump fails", probability=0.1)
        rewritten = tree_with(
            {"id": pump, "name": "Pump fails", "probability": 0.1},
            {"id": "ai_new", "name": "Added by AI", "probability": 0.01},
        )
        blocked = Blocked(json.dumps(rewritten))
        monkeypatch.setattr(provider, "send_message", blocked)

        thread, outcome = in_background(app, "post", "/api/ai/update", {})
        try:
            assert blocked.inside.wait(5)
            client.patch("/api/nodes/%s" % pump, json={"probability": 0.9})
            client.post("/api/undo")
        finally:
            blocked.release.set()
            thread.join(10)

        assert outcome["response"].status_code == 200, body(outcome["response"])
        assert [c[0] for c in children(client)] == [pump, "ai_new"]


# --------------------------------------------------------------------------
# AI-02: proposals made for one document were applied to the next one
# --------------------------------------------------------------------------


class TestProposalsBelongToTheirDocument:
    """``root_0`` is the first child of every tree: after New or Open a
    pending proposal's ids name unrelated nodes. Applying an 'edit' made for
    "Pump fails" renamed document B's "Valve stuck", multiplied its
    probability by 20 000 and wiped its notes."""

    @pytest.fixture
    def proposed(self, client, provider, monkeypatch):
        pump = add(client, name="Pump fails", probability=0.01)
        monkeypatch.setattr(provider, "send_message", replies(edit_reply(pump, "Pump fails")))
        changes = body(client.post("/api/ai/chat", json={"message": "review"}))["changes"]
        assert [c["targetId"] for c in changes] == [pump]
        return changes[0]["index"]

    def test_after_open_the_proposal_is_refused(self, client, proposed, tmp_path):
        path = write_document(tmp_path / "plant_b.json")
        assert client.post("/api/file/open", json={"path": str(path)}).status_code == 200
        before = children(client)

        response = client.post("/api/ai/changes/apply", json={"indices": [proposed]})

        assert response.status_code == 400
        assert error_code(response) == "AI_CHANGE_REJECTED"
        message = body(response)["error"]["detail"]["rejected"][0]["message"]
        assert "different analysis" in message
        assert children(client) == before == [("root_0", "Valve stuck", 1e-5, "reviewed value")]
        assert body(client.get("/api/state"))["dirty"] is False

    def test_after_new_the_proposal_is_refused(self, client, proposed):
        assert client.post("/api/new", json={"force": True}).status_code == 200
        add(client, name="Unrelated", probability=0.5)  # gets root_0 again

        response = client.post("/api/ai/changes/apply", json={"indices": [proposed]})

        assert response.status_code == 400
        assert children(client) == [("root_0", "Unrelated", 0.5, "")]

    def test_undo_and_redo_keep_the_document_and_its_proposals(self, client, proposed):
        add(client, name="Scratch")
        client.post("/api/undo")
        client.post("/api/redo")

        response = client.post("/api/ai/changes/apply", json={"indices": [proposed]})

        assert response.status_code == 200, body(response)
        assert children(client)[0][1:3] == ("Pump fails", 0.2)

    def test_analyze_proposals_are_tagged_too(self, client, provider, monkeypatch, tmp_path):
        pump = add(client, name="Pump fails", probability=0.01)
        monkeypatch.setattr(provider, "send_message", replies(edit_reply(pump, "Pump fails")))
        index = body(client.post("/api/ai/analyze", json={}))["changes"][0]["index"]
        path = write_document(tmp_path / "plant_b.json")
        client.post("/api/file/open", json={"path": str(path)})

        assert client.post("/api/ai/changes/apply", json={"indices": [index]}).status_code == 400

    def test_a_reply_that_arrives_after_open_belongs_to_the_old_document(
        self, app, client, provider, monkeypatch, tmp_path
    ):
        """The proposal is for the tree the model was shown, not for the one
        that happens to be open when its answer arrives."""
        pump = add(client, name="Pump fails", probability=0.01)
        blocked = Blocked(edit_reply(pump, "Pump fails"))
        monkeypatch.setattr(provider, "send_message", blocked)

        thread, outcome = in_background(app, "post", "/api/ai/chat", {"message": "review"})
        try:
            assert blocked.inside.wait(5)
            path = write_document(tmp_path / "plant_b.json")
            client.post("/api/file/open", json={"path": str(path)})
        finally:
            blocked.release.set()
            thread.join(10)
        index = body(outcome["response"])["changes"][0]["index"]

        assert client.post("/api/ai/changes/apply", json={"indices": [index]}).status_code == 400
        assert children(client) == [("root_0", "Valve stuck", 1e-5, "reviewed value")]


# --------------------------------------------------------------------------
# AI-03: a NaN probability or non-text notes from the model were installed
# --------------------------------------------------------------------------


class TestModelOutputIsValidatedLikeUserInput:
    """``nan < 0`` and ``nan > 1`` are both False, so the vendored range
    checks let NaN through (JSON ``NaN`` or the string ``"nan"``); one NaN
    leaf made the top event NaN (null in the browser) and the MCUB 0.0.
    Non-text notes were stored as given and broke the XML export."""

    @pytest.mark.parametrize("literal", ["NaN", '"nan"'])
    def test_a_nan_probability_edit_is_refused(self, client, provider, monkeypatch, literal):
        pump = add(client, name="Pump fails", probability=0.01)
        monkeypatch.setattr(
            provider, "send_message", replies(edit_reply(pump, "Pump fails", literal))
        )
        index = body(client.post("/api/ai/chat", json={"message": "x"}))["changes"][0]["index"]

        response = client.post("/api/ai/changes/apply", json={"indices": [index]})

        assert response.status_code == 400
        assert "probability" in body(response)["error"]["detail"]["rejected"][0]["message"]
        assert get_state().core.find_node_by_id(pump)["probability"] == 0.01
        assert get_state().core.get_data()["calculatedProbability"] == pytest.approx(0.01)

    def test_a_nan_probability_add_is_refused(self, client, provider, monkeypatch):
        monkeypatch.setattr(provider, "send_message", replies(add_reply("NaN")))
        index = body(client.post("/api/ai/chat", json={"message": "x"}))["changes"][0]["index"]

        response = client.post("/api/ai/changes/apply", json={"indices": [index]})

        assert response.status_code == 400
        assert get_state().core.find_node_by_id("corrosion") is None

    @pytest.mark.parametrize("literal", ['["a", "b"]', "12"])
    def test_notes_that_are_not_text_are_refused(self, client, provider, monkeypatch, literal):
        pump = add(client, name="Pump fails", probability=0.01, notes="vendor data")
        monkeypatch.setattr(
            provider, "send_message",
            replies(edit_reply(pump, "Pump fails", "0.02", literal)),
        )
        index = body(client.post("/api/ai/chat", json={"message": "x"}))["changes"][0]["index"]

        response = client.post("/api/ai/changes/apply", json={"indices": [index]})

        assert response.status_code == 400
        assert "notes" in body(response)["error"]["detail"]["rejected"][0]["message"]
        assert get_state().core.find_node_by_id(pump)["notes"] == "vendor data"

    def test_a_valid_proposal_in_the_same_batch_still_applies(
        self, client, provider, monkeypatch
    ):
        pump = add(client, name="Pump fails", probability=0.01)
        monkeypatch.setattr(
            provider, "send_message",
            replies(edit_reply(pump, "Pump fails", "NaN") + "\n" + add_reply()),
        )
        changes = body(client.post("/api/ai/chat", json={"message": "x"}))["changes"]

        payload = body(client.post(
            "/api/ai/changes/apply", json={"indices": [c["index"] for c in changes]}
        ))

        assert [r["changeType"] for r in payload["rejected"]] == ["edit"]
        assert [a["changeType"] for a in payload["applied"]] == ["add"]
        assert get_state().core.find_node_by_id(pump)["probability"] == 0.01

    @pytest.mark.parametrize(
        "field,value,needle",
        [
            ("probability", float("nan"), "probability"),
            ("probability", "nan", "probability"),
            ("notes", {"x": 1}, "notes"),
            ("notes", ["a"], "notes"),
            ("houseState", "yes", "houseState"),
            ("gateType", "MAYBE", "gateType"),
        ],
    )
    def test_an_update_carrying_it_is_rejected_and_names_the_node(
        self, client, provider, monkeypatch, field, value, needle
    ):
        pump = add(client, name="Pump fails", probability=0.01, notes="vendor data")
        node = {"id": pump, "name": "Pump fails", "probability": 0.01, "notes": "vendor data"}
        node[field] = value
        monkeypatch.setattr(provider, "send_message", replies(json.dumps(tree_with(node))))
        before = body(client.get("/api/state"))

        response = client.post("/api/ai/update", json={})

        assert response.status_code == 400
        assert error_code(response) == "AI_UPDATE_REJECTED"
        detail = body(response)["error"]["detail"]
        assert detail["nodeId"] == pump
        assert needle in detail["validatorMessage"]
        after = body(client.get("/api/state"))
        assert after["tree"] == before["tree"]
        assert after["canUndo"] == before["canUndo"] and after["canRedo"] == before["canRedo"]

    def test_valid_new_keys_in_an_update_are_still_accepted(self, client, provider, monkeypatch):
        update = tree_with(
            {"id": "vote", "name": "2oo3", "logicGate": "OR", "gateType": "KOFN", "k": 2,
             "children": [
                 {"id": n, "name": n, "type": "Event", "probability": 0.1, "logicGate": "OR",
                  "notes": "", "links": [], "children": []} for n in ("a", "b", "c")
             ]},
            {"id": "house", "name": "Maintenance", "eventKind": "house", "houseState": True},
        )
        monkeypatch.setattr(provider, "send_message", replies(json.dumps(update)))

        response = client.post("/api/ai/update", json={})

        assert response.status_code == 200, body(response)
        vote = get_state().core.find_node_by_id("vote")
        assert vote["calculatedProbability"] == pytest.approx(3 * 0.1 ** 2 * 0.9 + 0.1 ** 3)


# --------------------------------------------------------------------------
# AI-04: "Applied 3 of 3" for a batch where two of three were rejected
# --------------------------------------------------------------------------


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _chat_source():
    return (STATIC / "chat.js").read_text(encoding="utf-8")


@needs_node
def test_the_applied_count_is_what_the_server_applied():
    """``applied`` is the list of applied records; ``Number([{...}])`` is NaN,
    so the old code fell back to the number of ticked boxes."""
    fn = re.search(r"^function appliedCount\(.*?\n\}", _chat_source(), re.S | re.M)
    assert fn, "chat.js has no top-level appliedCount()"
    cases = [
        [{"applied": [{"index": 0}], "rejected": [{"index": 1}, {"index": 2}]}, 3],
        [{"applied": [{"index": 0}, {"index": 2}], "rejected": [{"index": 1}]}, 3],
        [{"applied": 2}, 3],
        [{}, 3],
        [None, 2],
    ]
    script = fn.group(0) + "\nconsole.log(JSON.stringify(%s.map((c) => appliedCount(c[0], c[1]))));" % json.dumps(cases)
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [1, 2, 2, 3, 2]


def test_a_partial_apply_shows_what_was_rejected():
    body_src = re.search(
        r"async function applyChanges\(handle, total\) \{(.*?)\n  \}\n", _chat_source(), re.S
    ).group(1)
    assert "appliedCount(result, indices.length)" in body_src
    assert "Number(result.applied)" not in body_src
    assert "showDiagnostics({ rejected: result.rejected })" in body_src


# --------------------------------------------------------------------------
# AI-05: a key quoted in a provider error leaked if it was cleared mid-call
# --------------------------------------------------------------------------


class TestTheKeyIsScrubbedEvenIfClearedMidCall:
    """scrub() redacted only the key stored when the response was built. A
    call still out when the user pressed Clear in AI settings answered after
    its key was gone, so an error quoting it went to the browser verbatim."""

    @pytest.mark.parametrize("path,payload", [
        ("/api/ai/chat", {"message": "hi"}),
        ("/api/ai/analyze", {}),
        ("/api/ai/update", {}),
    ])
    def test_the_key_in_hand_is_redacted(self, app, client, provider, monkeypatch, path, payload):
        inside, release = threading.Event(), threading.Event()

        def leaky(api_key, endpoint, model, messages, max_tokens=2000):
            inside.set()
            release.wait(10)
            return None, "request to https://gw.example/v1?key=%s failed: 401" % api_key

        monkeypatch.setattr(provider, "send_message", leaky)

        thread, outcome = in_background(app, "post", path, payload)
        try:
            assert inside.wait(5)
            assert client.delete("/api/ai/credentials").status_code == 200
        finally:
            release.set()
            thread.join(10)

        text = outcome["response"].get_data(as_text=True)
        assert API_KEY not in text
        assert ai_bridge.REDACTED in text


# --------------------------------------------------------------------------
# AI-06: Cancel/Escape during Test & Save left the chat refusing a saved key
# --------------------------------------------------------------------------


@pytest.mark.parametrize("function,request_call", [
    ("testAndSave", "await api.post('/ai/credentials'"),
    ("clearCredentials", "await api.del('/ai/credentials');"),
])
def test_closing_the_dialog_mid_request_still_refreshes_the_shell(function, request_call):
    """The dialog stays closable while the key is being tested (seconds); the
    save still lands on the server. The `if (closed) return;` that followed
    skipped refreshShell(), so aiConfigured stayed false in the store and the
    chat answered every message with "No provider is set up yet" (seen in
    Chromium with a mocked provider) until the page was reloaded."""
    src = (STATIC / "aisettings.js").read_text(encoding="utf-8")
    body_src = re.search(
        r"  async function %s\(\) \{(.*?)\n  \}\n" % function, src, re.S
    ).group(1)
    after = body_src[body_src.index(request_call):]
    closed_branch = re.search(r"if \(closed\) \{(.*?)\n      \}", after, re.S)
    assert closed_branch, "the closed-dialog branch after the request is gone"
    assert after.index(closed_branch.group(0)) < after.index("setBusy(false)")
    assert "await refreshShell();" in closed_branch.group(1)
    assert "return;" in closed_branch.group(1)


# --------------------------------------------------------------------------
# AI-07 / AI-11, divergence D21: Anthropic replies from thinking models
# --------------------------------------------------------------------------


def _claude_message(*blocks, stop_reason="end_turn"):
    """A real anthropic.types.Message, so a ThinkingBlock really has no .text."""
    from anthropic.types import Message

    return Message.model_validate({
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": list(blocks), "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    })


THINKING = {"type": "thinking", "thinking": "", "signature": "EqQBCkYIARgC"}


@pytest.fixture
def fake_anthropic(monkeypatch):
    """anthropic.Anthropic replaced by a recorder: no socket is ever opened."""
    anthropic = pytest.importorskip("anthropic")
    seen = {"clients": [], "creates": []}
    answer = {"message": _claude_message({"type": "text", "text": "ok"}), "models": []}

    class FakeAnthropic:
        def __init__(self, **kwargs):
            seen["clients"].append(kwargs)
            self.messages = type("Messages", (), {"create": staticmethod(self._create)})()
            self.models = type("Models", (), {"list": staticmethod(self._list)})()

        @staticmethod
        def _create(**kwargs):
            seen["creates"].append(kwargs)
            return answer["message"]

        @staticmethod
        def _list(**kwargs):
            if isinstance(answer["models"], Exception):
                raise answer["models"]
            return answer["models"]

    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    return seen, answer


class TestAnthropicRepliesFromThinkingModels:
    """claude-opus-5 (the pre-selected default) and the 5.x models think by
    default; the reply's content then starts with a `thinking` block, and
    response.content[0].text raised AttributeError -- every chat failed with
    "'ThinkingBlock' object has no attribute 'text'"."""

    MESSAGES = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "Analyze"}]

    def test_the_text_blocks_are_the_reply(self, fake_anthropic):
        seen, answer = fake_anthropic
        answer["message"] = _claude_message(
            THINKING, {"type": "text", "text": "SUGGESTION: "}, {"type": "text", "text": "add corrosion"}
        )
        claude = AIProviderFactory.get_provider("Anthropic Claude")

        assert claude.send_message("k", "x", "claude-opus-5", self.MESSAGES) == (
            "SUGGESTION: add corrosion", None
        )

    def test_no_text_is_an_error_that_names_the_stop_reason(self, fake_anthropic):
        seen, answer = fake_anthropic
        answer["message"] = _claude_message(THINKING, stop_reason="max_tokens")
        claude = AIProviderFactory.get_provider("Anthropic Claude")

        text, error = claude.send_message("k", "x", "claude-opus-5", self.MESSAGES)

        assert text is None
        assert "no text" in error and "stop_reason: max_tokens" in error

    @pytest.mark.parametrize("requested,sent", [(2000, 16000), (10, 16000), (32000, 32000)])
    def test_thinking_gets_output_headroom(self, fake_anthropic, requested, sent):
        """Thinking tokens count against max_tokens: the handler's 2000 could
        all go to thinking. 16000 is the documented non-streaming default."""
        seen, _answer = fake_anthropic
        claude = AIProviderFactory.get_provider("Anthropic Claude")

        claude.send_message("k", "x", "claude-opus-5", self.MESSAGES, max_tokens=requested)

        assert seen["creates"][-1]["max_tokens"] == sent

    def test_no_sampling_parameter_is_sent(self, fake_anthropic):
        """temperature/top_p/top_k are a 400 on Opus 5.5/5/4.8/4.7 and Sonnet 5."""
        seen, _answer = fake_anthropic
        claude = AIProviderFactory.get_provider("Anthropic Claude")

        claude.send_message("k", "x", "claude-opus-5-5", self.MESSAGES)
        claude.test_connection("k", "x", "claude-opus-5-5")

        for call in seen["creates"]:
            assert not {"temperature", "top_p", "top_k"} & set(call)

    def test_a_chat_through_the_api_shows_the_text(self, app, credentials_home, fake_anthropic, monkeypatch):
        seen, answer = fake_anthropic
        answer["message"] = _claude_message(THINKING, {"type": "text", "text": "Looks complete."})
        claude = AIProviderFactory.get_provider("Anthropic Claude")
        monkeypatch.setattr(claude, "test_connection", lambda *a, **k: (True, "ok"))
        with app.test_client() as test_client:
            assert test_client.post("/api/ai/credentials", json={
                "provider": "Anthropic Claude", "apiKey": API_KEY, "model": "claude-opus-5"}).status_code == 200

            reply = body(test_client.post("/api/ai/chat", json={"message": "review"}))["reply"]

        assert reply == "Looks complete."


# --------------------------------------------------------------------------
# AI-16, divergence D22: Anthropic's model list comes from the Models API
# --------------------------------------------------------------------------


def _model_info(model_id):
    from anthropic.types import ModelInfo

    return ModelInfo.model_validate({
        "id": model_id, "created_at": "2026-08-01T00:00:00Z",
        "display_name": model_id, "type": "model",
    })


class TestAnthropicModelList:
    """get_available_models returned the built-in list without a request
    ("Anthropic doesn't provide a list_models endpoint"), and the dialog
    labelled it "Loaded from the provider."."""

    def test_the_live_list_is_asked_for(self, fake_anthropic):
        _seen, answer = fake_anthropic
        answer["models"] = [_model_info("claude-opus-5-5"), _model_info("claude-haiku-5-5")]

        models, warning = AIProviderFactory.get_provider("Anthropic Claude").get_available_models("k", "x")

        assert (models, warning) == (["claude-opus-5-5", "claude-haiku-5-5"], None)

    def test_any_failure_falls_back_to_the_built_in_list_and_says_so(self, fake_anthropic):
        _seen, answer = fake_anthropic
        answer["models"] = RuntimeError("401 invalid x-api-key")
        claude = AIProviderFactory.get_provider("Anthropic Claude")

        models, warning = claude.get_available_models("k", "x")

        assert models == claude.get_default_models()
        assert "401 invalid x-api-key" in warning

    def test_the_built_in_list_leads_with_the_current_models(self):
        assert AIProviderFactory.get_provider("Anthropic Claude").get_default_models() == [
            "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5", "claude-sonnet-5",
        ]

    def test_the_settings_dialog_gets_the_live_list(self, app, fake_anthropic, monkeypatch):
        _seen, answer = fake_anthropic
        answer["models"] = [_model_info("claude-opus-5-5"), _model_info("claude-sonnet-5-5")]
        claude = AIProviderFactory.get_provider("Anthropic Claude")
        monkeypatch.setattr(claude, "test_connection", lambda *a, **k: (True, "ok"))
        with app.test_client() as test_client:
            test_client.post("/api/ai/credentials", json={"provider": "Anthropic Claude", "apiKey": API_KEY})

            payload = body(test_client.get("/api/ai/models?provider=Anthropic%20Claude"))

        assert payload["source"] == "live"
        assert payload["models"] == ["claude-opus-5-5", "claude-sonnet-5-5"]


# --------------------------------------------------------------------------
# A loopback HTTP server that answers like the provider APIs, for driving the
# real SDKs without a network (used by the D23 and D24 tests)
# --------------------------------------------------------------------------

_OPENAI_CHAT = {
    "id": "chatcmpl-1", "object": "chat.completion", "created": 0, "model": "m",
    "choices": [{"index": 0, "finish_reason": "stop",
                 "message": {"role": "assistant", "content": "openai says hi"}}],
}
_CLAUDE_MESSAGE = {
    "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
    "content": [{"type": "text", "text": "claude says hi"}], "stop_reason": "end_turn",
    "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1},
}
_GEMINI_REPLY = {"candidates": [{"content": {"parts": [{"text": "gemini says hi"}], "role": "model"},
                                 "finishReason": "STOP", "index": 0}]}


@pytest.fixture
def loopback(monkeypatch):
    """``(base_url, requests, server)``; ``server.hang = True`` makes every
    request wait (without answering) until the test ends."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    requests = []
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _answer(self, payload, status=200):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _route(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            requests.append({"method": self.command, "path": self.path,
                             "body": json.loads(raw) if raw else None})
            if server.hang:
                release.wait(30)
                return
            if server.delay:
                time.sleep(server.delay)
            path = self.path
            if "/chat/completions" in path and not path.startswith("/openai/openai/"):
                return self._answer(_OPENAI_CHAT)
            if path.startswith("/v1/messages"):
                return self._answer(_CLAUDE_MESSAGE)
            if ":generateContent" in path:
                return self._answer(_GEMINI_REPLY)
            return self._answer({"error": {"message": "no route " + path}}, 404)

        do_GET = do_POST = _route

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.hang = False
    server.delay = 0.0
    # A short poll: shutdown() waits up to one poll interval, per test.
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    base = "http://127.0.0.1:%d" % server.server_address[1]
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    yield base, requests, server
    release.set()
    server.shutdown()
    server.server_close()


# --------------------------------------------------------------------------
# AI-08, divergence D23: the documented Azure endpoint never worked
# --------------------------------------------------------------------------


class TestAzureEndpointForms:
    """docs/MICROSOFT_COPILOT_SETUP.md says to enter
    https://{resource}.openai.azure.com/openai/deployments/{deployment}. The
    provider passed ".../openai" as azure_endpoint, the SDK appends "/openai"
    itself, and every request went to /openai/openai/deployments/... -- 404."""

    @pytest.mark.parametrize("suffix", [
        "/openai/deployments/fta-dep",
        "/openai/deployments/fta-dep/",
        "/openai/deployments/fta-dep/chat/completions?api-version=2024-08-01-preview",
        "/openai",
        "/openai/",
        "/",
        "",
    ])
    def test_the_request_reaches_the_deployment(self, loopback, suffix):
        pytest.importorskip("openai")
        base, requests, _server = loopback
        azure = AIProviderFactory.get_provider("Microsoft Copilot")
        endpoint = base + suffix
        model = "fta-dep"  # the deployment when the URL names none

        ok, message = azure.test_connection("k", endpoint, model)
        reply = azure.send_message("k", endpoint, model, [{"role": "user", "content": "hi"}])

        assert ok, message
        assert reply == ("openai says hi", None)
        assert [r["path"].split("?")[0] for r in requests] == [
            "/openai/deployments/fta-dep/chat/completions"] * 2


# --------------------------------------------------------------------------
# AI-09, divergence D24: every SDK client has a deadline
# --------------------------------------------------------------------------


def _provider_call(name, base, monkeypatch):
    """A send_message call for provider ``name`` aimed at the loopback server."""
    messages = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
    provider = AIProviderFactory.get_provider(name)
    if name == "OpenAI":
        pytest.importorskip("openai")
        return lambda: provider.send_message("k", base + "/v1", "gpt-4o", messages)
    if name == "Microsoft Copilot":
        pytest.importorskip("openai")
        return lambda: provider.send_message("k", base, "fta-dep", messages)
    if name == "Anthropic Claude":
        pytest.importorskip("anthropic")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", base)
        return lambda: provider.send_message("k", "ignored", "claude-opus-5-5", messages)
    pytest.importorskip("google.genai")
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", base + "/")
    return lambda: provider.send_message("AIzaKey", "ignored", "gemini-2.5-flash", messages)


PROVIDERS = ["OpenAI", "Microsoft Copilot", "Anthropic Claude", "Google Gemini"]


class TestEveryProviderCallHasADeadline:
    """No client was given a timeout: OpenAI and Anthropic wait 600 s per try
    with 2 retries (a timeout is retried), google-genai waits forever. A call
    the bridge had given up on kept the single AI call slot, so every AI
    request -- Test & Save of another provider included -- was AI_BUSY for up
    to half an hour, and with Gemini until the editor was restarted."""

    @pytest.mark.parametrize("name", PROVIDERS)
    def test_a_hung_provider_lets_go(self, loopback, monkeypatch, name):
        import ai_providers

        base, requests, server = loopback
        server.hang = True
        monkeypatch.setattr(ai_providers, "REQUEST_TIMEOUT_SECONDS", 0.3, raising=False)
        call = _provider_call(name, base, monkeypatch)
        outcome = {}
        worker = threading.Thread(target=lambda: outcome.update(result=call()), daemon=True)

        worker.start()
        worker.join(10)

        assert "result" in outcome, "%s was still waiting after 10 s" % name
        text, error = outcome["result"]
        assert text is None and error
        assert 1 <= len(requests) <= ai_providers.MAX_RETRIES + 1

    @pytest.mark.parametrize("name", PROVIDERS)
    def test_a_slow_answer_inside_the_deadline_arrives(self, loopback, monkeypatch, name):
        """Pins the unit: google-genai takes milliseconds, the others seconds."""
        import ai_providers

        base, _requests, server = loopback
        server.delay = 0.5
        monkeypatch.setattr(ai_providers, "REQUEST_TIMEOUT_SECONDS", 5.0, raising=False)

        text, error = _provider_call(name, base, monkeypatch)()

        assert error is None and text.endswith("says hi")

    def test_the_deadline_is_the_apps_ai_timeout(self):
        import ai_providers

        from fta_web import config

        assert ai_providers.REQUEST_TIMEOUT_SECONDS == config.AI_TIMEOUT_SECONDS
        assert ai_providers.MAX_RETRIES <= 1


# --------------------------------------------------------------------------
# AI-10, divergence D25: an empty reply is not an assistant turn
# --------------------------------------------------------------------------


class TestAnEmptyReplyIsNotKept:
    """A reply with no text (a Gemini 2.5 model that spent max_output_tokens on
    thinking, a safety block) was appended to the history as
    {"role": "assistant", "content": None} before parsing failed on it, so the
    user read "expected string or bytes-like object" and every later request
    carried a null turn."""

    @pytest.mark.parametrize("empty", [None, "", "  \n"])
    def test_the_user_is_told_and_the_history_is_unchanged(self, client, provider, monkeypatch, empty):
        monkeypatch.setattr(provider, "send_message", lambda *a, **k: (empty, None))
        before = list(ai_bridge.get_handler().conversation_history)

        reply = body(client.post("/api/ai/chat", json={"message": "first"}))["reply"]

        assert reply.startswith("AI Error:") and "empty reply" in reply
        assert ai_bridge.get_handler().conversation_history == before

    def test_the_next_request_carries_no_empty_turn(self, client, provider, monkeypatch):
        monkeypatch.setattr(provider, "send_message", lambda *a, **k: (None, None))
        client.post("/api/ai/chat", json={"message": "first"})
        seen = {}

        def capture(api_key, endpoint, model, messages, max_tokens=2000):
            seen["messages"] = messages
            return "fine", None

        monkeypatch.setattr(provider, "send_message", capture)
        client.post("/api/ai/chat", json={"message": "second"})

        assert [m["role"] for m in seen["messages"]] == ["system", "user"]
        assert all(isinstance(m["content"], str) and m["content"] for m in seen["messages"])


# --------------------------------------------------------------------------
# AI-15, divergence D26: OpenAI reasoning models
# --------------------------------------------------------------------------


class TestOpenAIReasoningModels:
    """The installed openai SDK documents max_tokens as "deprecated in favor of
    `max_completion_tokens`, and ... not compatible with o-series models"; the
    live model list offers gpt-5* (its filter is "gpt" in the id). Test & Save
    and every chat sent max_tokens (and temperature=0.7) to them."""

    MESSAGES = [{"role": "user", "content": "hi"}]

    def _bodies(self, loopback, model, provider_name="OpenAI", suffix="/v1"):
        pytest.importorskip("openai")
        base, requests, _server = loopback
        provider = AIProviderFactory.get_provider(provider_name)
        assert provider.test_connection("k", base + suffix, model)[0]
        assert provider.send_message("k", base + suffix, model, self.MESSAGES, max_tokens=2000)[1] is None
        return [r["body"] for r in requests]

    @pytest.mark.parametrize("model", ["gpt-5", "gpt-5-mini", "GPT-5", "o3", "o4-mini", "o1-preview", "openai/o3-mini"])
    def test_reasoning_models_get_max_completion_tokens_and_no_temperature(self, loopback, model):
        test_body, chat_body = self._bodies(loopback, model)

        assert test_body["max_completion_tokens"] == 10 and "max_tokens" not in test_body
        assert chat_body["max_completion_tokens"] == 2000 and "max_tokens" not in chat_body
        assert "temperature" not in test_body and "temperature" not in chat_body

    @pytest.mark.parametrize("model", ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "omni-local", "llama3"])
    def test_other_models_are_sent_as_before(self, loopback, model):
        test_body, chat_body = self._bodies(loopback, model)

        assert test_body["max_tokens"] == 10
        assert chat_body["max_tokens"] == 2000 and chat_body["temperature"] == 0.7
        assert "max_completion_tokens" not in chat_body

    def test_azure_deployments_are_unchanged(self, loopback):
        """A deployment name says nothing reliable about the model behind it."""
        _test_body, chat_body = self._bodies(loopback, "gpt-5", "Microsoft Copilot", suffix="")

        assert chat_body["max_tokens"] == 2000 and chat_body["temperature"] == 0.7


# --------------------------------------------------------------------------
# AI_DOCUMENT_CHANGED is read by the user: it has a Japanese message
# --------------------------------------------------------------------------


def test_the_document_changed_refusal_is_localised(app, client, provider, monkeypatch):
    pump = add(client, name="Pump fails", probability=0.1)
    blocked = Blocked(json.dumps(tree_with({"id": pump, "name": "Pump fails", "probability": 0.1})))
    monkeypatch.setattr(provider, "send_message", blocked)

    thread, outcome = in_background(app, "post", "/api/ai/update?lang=ja", {})
    try:
        assert blocked.inside.wait(5)
        client.patch("/api/nodes/%s" % pump, json={"probability": 0.9})
    finally:
        blocked.release.set()
        thread.join(10)

    error = body(outcome["response"])["error"]
    assert error["code"] == "AI_DOCUMENT_CHANGED"
    assert any(ord(c) > 0x3000 for c in error["message"]), error["message"]


# --------------------------------------------------------------------------
# AI-13: an AI probability edit on a derived probability is refused
# --------------------------------------------------------------------------


def _probability_edit(node_id, name, probability="0.3"):
    return (
        "SUGGESTION: Revise\nDESCRIPTION: field data.\nACTION: edit\nTARGET: %s\n"
        'DATA: {"id": "%s", "name": "%s", "probability": %s}\n' % (node_id, node_id, name, probability)
    )


class TestDerivedProbabilitiesAreNotEditedByTheAI:
    """The engine recomputes the probability of a rate/standby/repairable event,
    a house event and a transfer gate on every recalculation, so an AI edit of
    it was reported as "✓ Updated ...: probability" and silently overruled."""

    def _apply(self, client, provider, monkeypatch, reply):
        monkeypatch.setattr(provider, "send_message", replies(reply))
        index = body(client.post("/api/ai/chat", json={"message": "x"}))["changes"][0]["index"]
        return client.post("/api/ai/changes/apply", json={"indices": [index]})

    @pytest.mark.parametrize("fields,needle", [
        ({"quant": {"model": "rate", "lambda": 1e-6, "T": 1000}}, "rate model"),
        ({"quant": {"model": "standby", "lambda": 1e-4, "tau": 100}}, "standby model"),
        ({"quant": {"model": "repairable", "lambda": 1e-4, "mttr": 8}}, "repairable model"),
        ({"eventKind": "house", "houseState": True}, "house event"),
    ])
    def test_the_change_is_rejected_with_what_to_edit_instead(
        self, client, provider, monkeypatch, fields, needle
    ):
        node_id = add(client, name="Derived", probability=0.5, **fields)
        before = json.dumps(get_state().core.find_node_by_id(node_id), sort_keys=True)

        response = self._apply(client, provider, monkeypatch, _probability_edit(node_id, "Derived"))

        assert response.status_code == 400
        message = body(response)["error"]["detail"]["rejected"][0]["message"]
        assert needle in message and "instead" in message
        assert json.dumps(get_state().core.find_node_by_id(node_id), sort_keys=True) == before

    def test_a_transfer_gate_is_rejected(self, client, provider, monkeypatch):
        target = add(client, name="Target", probability=0.2)
        transfer = add(client, name="Transfer", gateType="TRANSFER", transferTo=target)

        response = self._apply(client, provider, monkeypatch, _probability_edit(transfer, "Transfer"))

        assert response.status_code == 400
        assert "transfer gate" in body(response)["error"]["detail"]["rejected"][0]["message"]
        assert get_state().core.find_node_by_id(transfer)["probability"] == pytest.approx(0.2)

    def test_a_model_that_cannot_be_evaluated_does_not_derive_anything(self, client, provider, monkeypatch):
        """quant.model rate without lambda keeps the entered probability."""
        node_id = add(client, name="Incomplete", probability=0.5, quant={"model": "rate"})

        response = self._apply(client, provider, monkeypatch, _probability_edit(node_id, "Incomplete"))

        assert response.status_code == 200, body(response)
        assert get_state().core.find_node_by_id(node_id)["probability"] == 0.3

    def test_an_edit_that_leaves_the_probability_alone_still_applies(self, client, provider, monkeypatch):
        node_id = add(client, name="Rate", probability=0.5, quant={"model": "rate", "lambda": 1e-6, "T": 1000})
        reply = ("SUGGESTION: Rename\nDESCRIPTION: clearer.\nACTION: edit\nTARGET: %s\n"
                 'DATA: {"id": "%s", "name": "Pump seal leak"}\n' % (node_id, node_id))

        response = self._apply(client, provider, monkeypatch, reply)

        assert response.status_code == 200, body(response)
        assert get_state().core.find_node_by_id(node_id)["name"] == "Pump seal leak"


# --------------------------------------------------------------------------
# AI-14: a new provider never receives the old conversation
# --------------------------------------------------------------------------


class TestANewProviderNeverReceivesTheOldConversation:
    """Clear in AI settings kept the server-side history, Clear Chat cannot
    run without credentials (400 AI_NOT_CONFIGURED, by design), and the next
    provider configured was sent the whole earlier conversation."""

    SECRET = "CONFIDENTIAL: pump P-101 seal defect"

    def _chat(self, client, provider, monkeypatch, reply="Noted."):
        monkeypatch.setattr(provider, "send_message", replies(reply))
        return body(client.post("/api/ai/chat", json={"message": self.SECRET}))

    def _history_sent_next(self, client, provider, monkeypatch):
        seen = {}

        def capture(api_key, endpoint, model, messages, max_tokens=2000):
            seen["messages"] = messages
            return "hello", None

        monkeypatch.setattr(provider, "send_message", capture)
        client.post("/api/ai/chat", json={"message": "next"})
        return [m["content"] for m in seen["messages"][1:-1]]  # between system and the new message

    def _configure(self, client, name, monkeypatch, **extra):
        other = AIProviderFactory.get_provider(name)
        monkeypatch.setattr(other, "test_connection", lambda *a, **k: (True, "ok"))
        response = client.post("/api/ai/credentials", json=dict({"provider": name, "apiKey": API_KEY}, **extra))
        assert response.status_code == 200, body(response)
        return other

    def test_clearing_the_credentials_forgets_it(self, client, provider, monkeypatch):
        self._chat(client, provider, monkeypatch)

        assert client.delete("/api/ai/credentials").status_code == 200

        assert ai_bridge.get_handler().conversation_history == []
        assert client.delete("/api/ai/conversation").status_code == 400  # unchanged
        gemini = self._configure(client, "Google Gemini", monkeypatch)
        assert self._history_sent_next(client, gemini, monkeypatch) == []

    def test_configuring_another_provider_forgets_it(self, client, provider, monkeypatch):
        self._chat(client, provider, monkeypatch)

        claude = self._configure(client, "Anthropic Claude", monkeypatch)

        assert self._history_sent_next(client, claude, monkeypatch) == []

    def test_another_endpoint_is_another_recipient(self, client, provider, monkeypatch):
        self._chat(client, provider, monkeypatch)

        self._configure(client, "OpenAI", monkeypatch, endpoint="https://models.github.ai/inference")

        assert self._history_sent_next(client, provider, monkeypatch) == []

    def test_a_new_key_for_the_same_provider_keeps_it(self, client, provider, monkeypatch):
        self._chat(client, provider, monkeypatch)

        self._configure(client, "OpenAI", monkeypatch)

        assert self._history_sent_next(client, provider, monkeypatch) == [self.SECRET, "Noted."]

    def test_pending_suggestions_survive_it(self, client, provider, monkeypatch):
        """They belong to the document, not to the provider."""
        index = self._chat(client, provider, monkeypatch, reply=add_reply())["changes"][0]["index"]

        self._configure(client, "Anthropic Claude", monkeypatch)

        assert client.post("/api/ai/changes/apply", json={"indices": [index]}).status_code == 200
        assert get_state().core.find_node_by_id("corrosion") is not None


# --------------------------------------------------------------------------
# AI-12: an update says what it did to the existing nodes
# --------------------------------------------------------------------------


class TestAnUpdateSaysWhatItDidToExistingNodes:
    """Update FTA replaces the tree (the tests above pin that); the docs said
    "Existing nodes are preserved; only additions are applied". A rewrite that
    dropped "Valve stuck" and raised a probability 5000x came back as a plain
    200 -- the user had to diff the tree by eye to see it."""

    def _document(self, client):
        ids = {
            "pump": add(client, name="Pump fails", probability=1e-5, notes="vendor data"),
            "valve": add(client, name="Valve stuck", probability=2e-4),
            "gate": add(client, name="Loss of flow", logicGate="AND", probability=1.0),
            "rate": add(client, name="Seal wear", probability=0.5,
                        quant={"model": "rate", "lambda": 1e-6, "T": 1000}),
        }
        for name, p in (("Filter clogged", 0.1), ("Line frozen", 0.2)):
            created = body(client.post("/api/nodes", json={"parentId": ids["gate"], "name": name, "probability": p}))
            ids[name] = created["nodeId"]
        return ids

    def _rewrite(self, ids):
        def leaf(node_id, name, p):
            return {"id": node_id, "name": name, "probability": p}

        gate = leaf(ids["gate"], "Loss of flow", 1.0)
        gate.update(logicGate="OR", children=[
            dict(leaf(ids["Filter clogged"], "Filter blocked", 0.1), type="Event", logicGate="OR",
                 notes="", links=[], children=[]),
            dict(leaf(ids["Line frozen"], "Line frozen", 0.2), type="Event", logicGate="OR",
                 notes="", links=[], children=[]),
        ])
        return tree_with(
            leaf(ids["pump"], "Pump fails", 0.05),        # probability raised
            gate,                                          # AND -> OR, a child renamed
            leaf(ids["rate"], "Seal wear", 0.9),          # its rate model wins again
            leaf("new_1", "Power loss", 1e-3),            # added; "Valve stuck" dropped
        )

    def test_removed_changed_and_added_nodes_are_reported(self, client, provider, monkeypatch):
        ids = self._document(client)
        monkeypatch.setattr(provider, "send_message", replies(json.dumps(self._rewrite(ids))))

        response = client.post("/api/ai/update", json={})

        assert response.status_code == 200, body(response)
        summary = body(response)["updateSummary"]
        assert summary["added"] == [{"id": "new_1", "name": "Power loss"}]
        assert summary["removed"] == [{"id": ids["valve"], "name": "Valve stuck"}]
        assert summary["changed"] == [
            {"id": ids["pump"], "name": "Pump fails", "fields": ["probability"]},
            {"id": ids["gate"], "name": "Loss of flow", "fields": ["gate"]},
            {"id": ids["Filter clogged"], "name": "Filter blocked", "fields": ["name"]},
        ]

    def test_a_changed_model_is_reported(self, client, provider, monkeypatch):
        rate = add(client, name="Seal wear", probability=0.5, quant={"model": "rate", "lambda": 1e-6, "T": 1000})
        node = {"id": rate, "name": "Seal wear", "probability": 0.5,
                "quant": {"model": "rate", "lambda": 1e-4, "T": 1000}}
        monkeypatch.setattr(provider, "send_message", replies(json.dumps(tree_with(node))))

        summary = body(client.post("/api/ai/update", json={}))["updateSummary"]

        assert summary["changed"] == [{"id": rate, "name": "Seal wear", "fields": ["probability", "quant"]}]


@needs_node
def test_the_chat_summarises_an_update_in_one_line():
    fn = re.search(r"^function summaryNames\(.*?\n\}\n.*?^function updateSummaryMessage\(.*?\n\}",
                   _chat_source(), re.S | re.M)
    assert fn, "chat.js has no top-level summaryNames()/updateSummaryMessage()"
    long_name = "x" * 60
    cases = [
        None,
        {"added": [{"id": "a"}], "changed": [], "removed": []},
        {"added": [], "changed": [], "removed": [{"id": "v", "name": "Valve stuck"}]},
        {"added": [], "changed": [{"id": "p", "name": "Pump fails"}], "removed": []},
        {"added": [], "changed": [{"id": "p", "name": long_name}],
         "removed": [{"id": str(i), "name": "n%d" % i} for i in range(7)]},
    ]
    consts = "\n".join(re.findall(r"^const SUMMARY_[A-Z_]+ = \d+;", _chat_source(), re.M))
    script = consts + "\n" + fn.group(0) + "\nconsole.log(JSON.stringify(%s.map(updateSummaryMessage)));" % json.dumps(cases)
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)

    assert out[0] is None
    assert out[1] == {"key": "ai.update.summary", "vars": {
        "added": 1, "changed": 0, "removed": 0, "removedNames": "", "changedNames": ""}}
    assert out[2]["key"] == "ai.update.summaryRemoved" and out[2]["vars"]["removedNames"] == "Valve stuck"
    assert out[3]["key"] == "ai.update.summaryChanged" and out[3]["vars"]["changedNames"] == "Pump fails"
    assert out[4]["key"] == "ai.update.summaryBoth"
    assert out[4]["vars"]["removedNames"] == "n0, n1, n2, n3, n4, …"
    assert out[4]["vars"]["changedNames"] == "x" * 39 + "…"


def test_the_update_summary_is_shown_and_translated():
    action = re.search(r"  function actionUpdate\(\) \{(.*?)\n  \}\n", _chat_source(), re.S).group(1)
    assert "updateSummaryMessage(result && result.updateSummary)" in action
    assert "say('system', summary.key, summary.vars)" in action
    sys.path.insert(0, str(REPO_ROOT / "fta_web" / "tests"))
    import test_catalog_parity

    en, ja = test_catalog_parity._catalogs()
    for key in ("ai.update.summary", "ai.update.summaryRemoved", "ai.update.summaryChanged",
                "ai.update.summaryBoth"):
        assert key in en and key in ja, key
        assert "Ctrl+Z" in en[key] and "Ctrl+Z" in ja[key]


# --------------------------------------------------------------------------
# AI-17: Microsoft Copilot's endpoint is not hidden under "Advanced"
# --------------------------------------------------------------------------


def test_the_azure_endpoint_is_shown_outside_advanced():
    """Microsoft Copilot has no usable default endpoint -- it is the user's own
    Azure resource -- but the field sat in the collapsed Advanced section with
    "Change it only for a proxy", pre-filled with YOUR-RESOURCE/YOUR-DEPLOYMENT."""
    src = (STATIC / "aisettings.js").read_text(encoding="utf-8")
    place = re.search(r"  function placeEndpoint\(entry\) \{(.*?)\n  \}\n", src, re.S)
    assert place, "aisettings.js has no placeEndpoint(entry)"
    body_src = place.group(1)
    assert "form.insertBefore(endpointBlock, advanced)" in body_src
    assert "advanced.appendChild(endpointBlock)" in body_src
    assert "'ai.endpoint.azureHint'" in body_src and "'ai.endpoint.hint'" in body_src
    select = re.search(r"  function selectProvider\(entry, options\) \{(.*?)\n  \}\n", src, re.S).group(1)
    assert "placeEndpoint(entry);" in select
    assert re.search(r"function isAzure\(name\) \{\s*return /microsoft\|azure/i\.test", src)

    sys.path.insert(0, str(REPO_ROOT / "fta_web" / "tests"))
    import test_catalog_parity

    en, ja = test_catalog_parity._catalogs()
    assert "ai.endpoint.azureHint" in en and "ai.endpoint.azureHint" in ja
    assert "openai.azure.com" in en["ai.endpoint.azureHint"]
