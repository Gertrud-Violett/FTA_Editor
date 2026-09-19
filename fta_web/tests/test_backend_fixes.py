"""
Regression tests for the web-backend findings in docs/CODE_REVIEW_2026-09.md:

* B-3  delete strips links into the deleted subtree; ids are never reused
       while they exist anywhere in the tree
* B-6  an AI full-JSON update is normalised before it is installed
* B-7  blueprint-level ApiError handlers localise like the app-level one
* B-8  the root guards use the loaded tree's own top-level id
* B-9  an all-rejected AI change batch costs no undo step
* B-11 the provider SDK probe does not run under state.lock

Each class builds the smallest app that exercises the path: the tree blueprint
alone for B-3/B-8, the AI blueprint on top for B-6/B-9, and both a bare
blueprint app and ``create_app`` for B-7, because the two register different
``ApiError`` handlers and both must localise.
"""
import json
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from AI_agent_handler import AICredentialManager  # noqa: E402
from ai_providers import AIProviderFactory  # noqa: E402

from fta_web import ai_bridge, i18n, state as state_module  # noqa: E402
from fta_web.state import get_state, reset_state  # noqa: E402

pytest.importorskip("flask")


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def tree_client():
    """The tree blueprint on a bare Flask app -- blueprint handlers only."""
    import flask

    from fta_web.routes.tree import tree_bp

    reset_state()
    app = flask.Flask(__name__)
    app.register_blueprint(tree_bp)
    app.config.update(TESTING=True)
    with app.test_client() as client:
        yield client


@pytest.fixture
def app_client():
    """The full application, with the app-level handler as well."""
    from fta_web.app import create_app

    reset_state()
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as client:
        yield client


def body(response):
    return json.loads(response.get_data(as_text=True))


def add(client, parent_id="root", name="Child", **kwargs):
    payload = {"parentId": parent_id, "name": name}
    payload.update(kwargs)
    response = client.post("/api/nodes", json=payload)
    assert response.status_code == 200, body(response)
    return body(response)


def node_view(client, node_id):
    return body(client.get(f"/api/nodes/{node_id}"))["node"]


def is_japanese(text):
    return any(ord(c) > 0x3000 for c in text)


# --------------------------------------------------------------------------
# B-3: delete strips links; ids are not reused while taken
# --------------------------------------------------------------------------


class TestDeleteStripsLinks:
    def test_the_review_scenario_cannot_retarget(self, tree_client):
        """X AND-links root_1 (0.1); delete root_1; add a child. The new
        child gets the id root_1 back, and X must not point at it."""
        c = tree_client
        # X first, so that root_1 is the last sibling and its index is the
        # one the generator hands out again after the delete. The link
        # dangles for one request, which is legal.
        x = add(
            c,
            name="X",
            probability=0.5,
            logicGate="AND",
            links=[{"target_id": "root_1", "relation": "AND"}],
        )["nodeId"]
        add(c, name="Target", probability=0.1)  # root_1
        assert node_view(c, x)["calculatedProbability"] == pytest.approx(0.05)

        deleted = body(c.delete("/api/nodes/root_1"))
        assert deleted["removedLinks"] == [
            {"nodeId": x, "targetId": "root_1", "relation": "AND"}
        ]
        assert node_view(c, x)["links"] == []
        assert node_view(c, x)["calculatedProbability"] == pytest.approx(0.5)

        # The deleted id is handed out again -- fine, nothing points at it.
        new_id = add(c, name="Unrelated", probability=0.9)["nodeId"]
        assert new_id == "root_1"
        assert node_view(c, x)["links"] == []
        assert node_view(c, x)["calculatedProbability"] == pytest.approx(0.5)

    def test_links_into_descendants_are_stripped_too(self, tree_client):
        c = tree_client
        add(c, name="Branch")  # root_0
        add(c, "root_0", name="Leaf")  # root_0_0
        add(c, name="Other")  # root_1
        c.patch(
            "/api/nodes/root_1",
            json={"links": [{"target_id": "root_0_0", "relation": "OR"}]},
        )
        # A link from inside the doomed subtree to outside is not reported:
        # it vanishes with its holder.
        c.patch(
            "/api/nodes/root_0_0",
            json={"links": [{"target_id": "root_1", "relation": "OR"}]},
        )

        removed = body(c.delete("/api/nodes/root_0"))["removedLinks"]

        assert removed == [{"nodeId": "root_1", "targetId": "root_0_0", "relation": "OR"}]
        assert node_view(c, "root_1")["links"] == []

    def test_unrelated_links_survive(self, tree_client):
        c = tree_client
        add(c, name="A")  # root_0
        add(c, name="B")  # root_1
        add(c, name="C")  # root_2
        c.patch(
            "/api/nodes/root_2",
            json={
                "links": [
                    {"target_id": "root_0", "relation": "OR"},
                    {"target_id": "root_1", "relation": "AND"},
                ]
            },
        )

        removed = body(c.delete("/api/nodes/root_0"))["removedLinks"]

        assert [r["targetId"] for r in removed] == ["root_0"]
        assert node_view(c, "root_2")["links"] == [
            {"target_id": "root_1", "relation": "AND", "targetName": "B"}
        ]

    def test_no_links_means_an_empty_list(self, tree_client):
        add(tree_client)
        payload = body(tree_client.delete("/api/nodes/root_0"))
        assert payload["removedLinks"] == []
        assert payload["deletedId"] == "root_0"
        assert set(payload) >= {"tree", "zeroNodes", "dirty", "canUndo", "canRedo"}

    def test_undo_brings_the_link_back(self, tree_client):
        c = tree_client
        add(c, name="Target")  # root_0
        add(c, name="Holder", links=[{"target_id": "root_0"}])  # root_1
        c.delete("/api/nodes/root_0")
        assert node_view(c, "root_1")["links"] == []

        assert c.post("/api/undo").status_code == 200

        assert node_view(c, "root_1")["links"][0]["target_id"] == "root_0"


class TestIdsAreNotReusedWhileTaken:
    def test_a_moved_child_keeps_its_id_reserved(self, tree_client):
        c = tree_client
        add(c, name="A")  # root_0
        add(c, name="B")  # root_1
        assert c.post("/api/nodes/root_1/move", json={"newParentId": "root_0"}).status_code == 200

        # Sibling-max would say root_1 again; that id lives under root_0 now.
        assert add(c, name="C")["nodeId"] == "root_2"
        ids = [n["id"] for n in body(c.get("/api/nodes"))["nodes"]]
        assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------
# B-8: the root guard follows the loaded tree
# --------------------------------------------------------------------------


class TestRootGuardFollowsTheTree:
    @pytest.fixture
    def renamed_root(self, tree_client):
        """A document whose top-level node is not called "root"."""
        state = get_state()
        with state.lock:
            state.core.set_data(
                {
                    "id": "top",
                    "name": "Top",
                    "type": "Event",
                    "probability": 1.0,
                    "logicGate": "OR",
                    "notes": "",
                    "links": [],
                    "children": [],
                }
            )
            state.core.recalculate_probabilities()
        return tree_client

    def test_the_actual_top_level_node_cannot_be_deleted(self, renamed_root):
        response = renamed_root.delete("/api/nodes/top")
        assert response.status_code == 400
        assert body(response)["error"]["code"] == "ROOT_PROTECTED"
        assert body(response)["error"]["detail"]["nodeId"] == "top"

    def test_the_actual_top_level_node_cannot_be_moved(self, renamed_root):
        add(renamed_root, parent_id="top", name="Child")
        response = renamed_root.post("/api/nodes/top/move", json={"newParentId": "top_0"})
        assert response.status_code == 400
        assert body(response)["error"]["code"] == "ROOT_PROTECTED"

    def test_the_literal_root_id_is_still_protected(self, tree_client):
        assert body(tree_client.delete("/api/nodes/root"))["error"]["code"] == "ROOT_PROTECTED"


# --------------------------------------------------------------------------
# B-7: blueprint handlers localise
# --------------------------------------------------------------------------


class TestBlueprintErrorsAreLocalised:
    JA_NOTHING_TO_UNDO = i18n._MESSAGES["NOTHING_TO_UNDO"]["ja"]

    def test_undo_on_an_empty_history_is_japanese_through_the_blueprint(self, tree_client):
        response = tree_client.post("/api/undo?lang=ja")
        assert response.status_code == 400
        error = body(response)["error"]
        assert error["code"] == "NOTHING_TO_UNDO"
        assert error["message"] == self.JA_NOTHING_TO_UNDO

    def test_undo_on_an_empty_history_is_japanese_through_the_app(self, app_client):
        response = app_client.post("/api/undo?lang=ja")
        assert response.status_code == 400
        assert body(response)["error"]["message"] == self.JA_NOTHING_TO_UNDO

    def test_accept_language_works_too(self, tree_client):
        response = tree_client.post("/api/redo", headers={"Accept-Language": "ja-JP,ja;q=0.9"})
        assert body(response)["error"]["message"] == i18n._MESSAGES["NOTHING_TO_REDO"]["ja"]

    def test_english_is_unchanged(self, tree_client):
        assert body(tree_client.post("/api/undo"))["error"]["message"] == "There is nothing to undo."

    def test_root_protected_is_japanese_with_detail_intact(self, tree_client):
        error = body(tree_client.delete("/api/nodes/root?lang=ja"))["error"]
        assert error["code"] == "ROOT_PROTECTED"
        assert is_japanese(error["message"])
        assert error["detail"] == {"nodeId": "root"}

    def test_path_rejected_is_japanese(self, tmp_path):
        """files.py's PathRejected handler builds its own ApiError; it has to
        go through the same localising path."""
        import flask

        from fta_web.routes.files import files_bp

        reset_state()
        root = tmp_path / "root"
        root.mkdir()
        app = flask.Flask(__name__)
        app.config.update(TESTING=True, FTA_FS_ROOT=root)
        app.register_blueprint(files_bp)
        with app.test_client() as client:
            response = client.post(
                "/api/file/open?lang=ja", json={"path": str(tmp_path / "outside.json")}
            )
        assert response.status_code == 400
        error = body(response)["error"]
        assert error["code"] == "PATH_REJECTED"
        assert error["message"] == i18n._MESSAGES["PATH_REJECTED"]["ja"]


# --------------------------------------------------------------------------
# B-6 / B-9: the AI blueprint
# --------------------------------------------------------------------------

PROVIDER_NAME = "OpenAI"

VALID_UPDATE = {
    "id": "root",
    "name": "Top event",
    "type": "Root",
    "probability": 1.0,
    "logicGate": "AND",
    "notes": "",
    "links": [],
    "children": [
        {
            "id": "n_1",
            "name": "Stringly typed",
            "type": "Event",
            "probability": "0.5",
            "logicGate": "OR",
            "notes": "",
            "links": [],
            "children": [],
        },
        {
            "id": "n_2",
            "name": "Also stringly",
            "type": "Event",
            "probability": "0.25",
            "logicGate": "OR",
            "notes": "",
            "links": [],
            "children": [],
        },
    ],
}

SUGGESTION_REPLY = """Corrosion is missing from this analysis.

SUGGESTION: Add a corrosion event
DESCRIPTION: Moisture ingress is not represented.
ACTION: add
TARGET: %s
DATA: {"id": "corrosion", "name": "Corrosion", "type": "Event", "probability": 0.05, "logicGate": "OR", "notes": ""}
"""


class TestAiBlueprint:
    @pytest.fixture(autouse=True)
    def credentials_home(self, tmp_path, monkeypatch):
        directory = tmp_path / "fta_editor_home"
        monkeypatch.setattr(AICredentialManager, "CREDENTIALS_DIR", directory)
        monkeypatch.setattr(
            AICredentialManager, "CREDENTIALS_FILE", directory / "ai_credentials.json"
        )

    @pytest.fixture
    def configured(self, monkeypatch):
        import flask

        from fta_web.routes.ai import ai_bp
        from fta_web.routes.tree import tree_bp

        reset_state()
        ai_bridge.reset_handler()
        app = flask.Flask(__name__)
        app.register_blueprint(tree_bp)
        app.register_blueprint(ai_bp)
        app.config.update(TESTING=True)

        provider = AIProviderFactory.get_provider(PROVIDER_NAME)
        monkeypatch.setattr(provider, "test_connection", lambda *a, **k: (True, "ok"))
        with app.test_client() as client:
            response = client.post(
                "/api/ai/credentials",
                json={"provider": PROVIDER_NAME, "apiKey": "sk-test-key-0000"},
            )
            assert response.status_code == 200, body(response)
            yield client, provider

    def _replies(self, text):
        def send_message(api_key, endpoint, model, messages, max_tokens=2000):
            return text, None

        return send_message

    # ---- B-6 ----------------------------------------------------------

    def test_an_update_with_string_probabilities_is_normalised(
        self, configured, monkeypatch
    ):
        client, provider = configured
        monkeypatch.setattr(provider, "send_message", self._replies(json.dumps(VALID_UPDATE)))

        response = client.post("/api/ai/update", json={})

        assert response.status_code == 200, body(response)
        stored = get_state().core.get_data()
        n_1, n_2 = stored["children"]
        assert n_1["probability"] == 0.5 and type(n_1["probability"]) is float
        assert n_2["probability"] == 0.25 and type(n_2["probability"]) is float
        # The numeric formatting that used to 500 on /api/dot works now.
        for child in stored["children"]:
            "%.1E" % child["probability"]
        assert stored["calculatedProbability"] == pytest.approx(0.125)

    def test_the_response_carries_the_normalised_tree(self, configured, monkeypatch):
        client, provider = configured
        monkeypatch.setattr(provider, "send_message", self._replies(json.dumps(VALID_UPDATE)))

        payload = body(client.post("/api/ai/update", json={}))

        assert payload["tree"]["children"][0]["probability"] == 0.5
        assert isinstance(payload["tree"]["children"][0]["probability"], float)

    # ---- B-9 ----------------------------------------------------------

    def test_an_all_rejected_batch_costs_no_undo_step(self, configured, monkeypatch):
        client, provider = configured
        # Build some history: one edit, undone, so there is a redo entry to lose.
        add(client, name="Scratch")
        assert client.post("/api/undo").status_code == 200
        assert body(client.get("/api/state"))["canRedo"] is True
        assert body(client.get("/api/state"))["canUndo"] is False

        monkeypatch.setattr(
            provider, "send_message", self._replies(SUGGESTION_REPLY % "nowhere")
        )
        client.post("/api/ai/chat", json={"message": "suggest"})
        response = client.post("/api/ai/changes/apply", json={"indices": [0]})

        assert response.status_code == 400
        assert body(response)["error"]["code"] == "AI_CHANGE_REJECTED"
        state_view = body(client.get("/api/state"))
        assert state_view["canUndo"] is False, "a no-op history entry was pushed"
        assert state_view["canRedo"] is True, "the redo stack was cleared"
        assert state_view["tree"]["children"] == []
        # And the redo entry still works.
        assert client.post("/api/redo").status_code == 200
        assert [c["name"] for c in body(client.get("/api/state"))["tree"]["children"]] == ["Scratch"]

    def test_a_partially_applied_batch_is_one_undo_step(self, configured, monkeypatch):
        client, provider = configured
        monkeypatch.setattr(provider, "send_message", self._replies(SUGGESTION_REPLY % "nowhere"))
        client.post("/api/ai/chat", json={"message": "first"})
        monkeypatch.setattr(provider, "send_message", self._replies(SUGGESTION_REPLY % "root"))
        client.post("/api/ai/chat", json={"message": "second"})

        response = client.post("/api/ai/changes/apply", json={"indices": [0, 1]})

        assert response.status_code == 200, body(response)
        payload = body(response)
        assert [r["index"] for r in payload["rejected"]] == [0]
        assert [a["index"] for a in payload["applied"]] == [1]
        assert payload["canUndo"] is True
        assert [c["id"] for c in payload["tree"]["children"]] == ["corrosion"]

        assert client.post("/api/undo").status_code == 200
        assert body(client.get("/api/state"))["tree"]["children"] == []
        assert body(client.get("/api/state"))["canUndo"] is False


# --------------------------------------------------------------------------
# core hand-off: load warnings are surfaced on open/import
# --------------------------------------------------------------------------


class TestLoadWarningsAreSurfaced:
    @pytest.fixture
    def files_client(self, tmp_path):
        import flask

        from fta_web.routes.files import files_bp

        reset_state()
        root = tmp_path / "root"
        root.mkdir()
        app = flask.Flask(__name__)
        app.config.update(TESTING=True, FTA_FS_ROOT=root)
        app.register_blueprint(files_bp)
        with app.test_client() as client:
            yield client, root

    @staticmethod
    def _leaf(node_id, name):
        return {
            "id": node_id,
            "name": name,
            "type": "Event",
            "probability": 0.1,
            "logicGate": "OR",
            "notes": "",
            "links": [],
            "children": [],
        }

    def _write(self, root, children):
        doc = {
            "title": "T",
            "date": "2026-01-01",
            "mode": "FTA",
            "tree": {**self._leaf("root", "Top"), "children": children},
        }
        path = root / "doc.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def test_a_clean_file_reports_no_warnings(self, files_client):
        client, root = files_client
        path = self._write(root, [self._leaf("a", "A")])
        payload = body(client.post("/api/file/open", json={"path": str(path)}))
        assert payload["ok"] is True
        assert payload["warnings"] == []

    def test_duplicate_ids_are_reported(self, files_client):
        client, root = files_client
        path = self._write(root, [self._leaf("e1", "first"), self._leaf("e1", "second")])
        payload = body(client.post("/api/file/open", json={"path": str(path)}))
        assert payload["ok"] is True
        kinds = [w["kind"] for w in payload["warnings"]]
        assert kinds == ["duplicate_id"]
        assert payload["warnings"][0]["old_id"] == "e1"
        assert payload["warnings"][0]["new_id"] == [c["id"] for c in payload["tree"]["children"]][1]

    def test_import_reports_them_too(self, files_client):
        import io

        client, _root = files_client
        doc = {"tree": {**self._leaf("root", "Top"), "children": [self._leaf("x", "1"), self._leaf("x", "2")]}}
        response = client.post(
            "/api/import/json",
            data={"file": (io.BytesIO(json.dumps(doc).encode("utf-8")), "up.json")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 200, body(response)
        assert [w["kind"] for w in body(response)["warnings"]] == ["duplicate_id"]


# --------------------------------------------------------------------------
# B-11: the SDK probe runs outside state.lock
# --------------------------------------------------------------------------


class TestProviderProbeIsOutsideTheLock:
    def test_to_dict_does_not_hold_the_lock_while_probing(self, monkeypatch):
        state = reset_state()
        seen = {}

        def probe():
            # An RLock cannot be asked who holds it, but a *different* thread
            # can try to take it: if that fails, this thread is holding it.
            def try_take():
                seen["free"] = state.lock.acquire(timeout=0)
                if seen["free"]:
                    state.lock.release()

            worker = threading.Thread(target=try_take)
            worker.start()
            worker.join()
            return {"OpenAI": True}

        monkeypatch.setattr(state_module, "_probe_provider_sdks", probe)

        payload = state.to_dict()

        assert seen["free"] is True, "the SDK probe ran under state.lock"
        assert payload["capabilities"]["aiProviders"] == {"OpenAI": True}

    def test_the_probe_still_runs_once(self, monkeypatch):
        calls = []

        real_import = state_module.importlib.import_module

        def counting_import(name, *args, **kwargs):
            calls.append(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(state_module, "_provider_sdk_cache", None)
        monkeypatch.setattr(state_module.importlib, "import_module", counting_import)

        first = state_module._probe_provider_sdks()
        second = state_module._probe_provider_sdks()

        assert first == second
        assert set(first) == set(state_module._PROVIDER_SDKS)
        assert len(calls) == len(state_module._PROVIDER_SDKS)
