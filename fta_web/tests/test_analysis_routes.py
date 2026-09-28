"""
Tests for the 1.7 Phase-0 blueprints: /api/analysis/*, /api/analysis/validate,
/api/report/docx and /api/fmea/*, plus the session warnings they surface and
the new /api/dot parameters.
"""
import json

import pytest

from fta_web import state as state_module
from fta_web.state import get_state, reset_state

pytest.importorskip("flask")


@pytest.fixture
def client(tmp_path):
    """The blueprints on a bare app, imported through the ``fta_web`` package.

    Not ``create_app()``: it imports the blueprints by bare module name
    (``routes.analysis``), which gives them a second ``state`` module -- and a
    second AppState singleton -- that this module's ``get_state`` never sees.
    """
    import flask

    from fta_web.routes.analysis import analysis_bp
    from fta_web.routes.files import files_bp
    from fta_web.routes.fmea import fmea_bp
    from fta_web.routes.render import render_bp
    from fta_web.routes.report import report_bp
    from fta_web.routes.tree import tree_bp
    from fta_web.routes.validate import validate_bp

    reset_state()
    app = flask.Flask(__name__)
    for bp in (tree_bp, files_bp, render_bp, analysis_bp, validate_bp, report_bp, fmea_bp):
        app.register_blueprint(bp)
    app.config.update(TESTING=True)
    get_state().fs_root = tmp_path
    with app.test_client() as test_client:
        yield test_client


def body(response):
    return json.loads(response.get_data(as_text=True))


def api(client, method, url, **kwargs):
    # create_app() without a token installs no security layer (test-only).
    return client.open(url, method=method, **kwargs)


def add(client, parent="root", **fields):
    fields.setdefault("name", "Event")
    response = api(client, "POST", "/api/nodes", json=dict(fields, parentId=parent))
    assert response.status_code == 200, body(response)
    return body(response)["nodeId"]


# ---- settings -------------------------------------------------------------------------


def test_settings_are_undoable_and_recalculate(client):
    nid = add(client, probability=0.5, quant={"model": "rate", "lambda": 1e-3})
    response = api(client, "POST", "/api/analysis/settings", json={"missionTime": 10})
    assert response.status_code == 200, body(response)
    payload = body(response)
    assert payload["analysis"]["missionTime"] == 10
    assert payload["canUndo"] is True and payload["dirty"] is True
    assert set(payload) >= {"tree", "zeroNodes", "canRedo", "sessionWarnings"}
    q10 = get_state().core.find_node_by_id(nid)["probability"]
    assert q10 == pytest.approx(1 - 2.718281828459045 ** -0.01, rel=1e-9)

    undone = body(api(client, "POST", "/api/undo"))
    assert undone["analysis"]["missionTime"] == 8760
    assert get_state().core.analysis["missionTime"] == 8760
    redone = body(api(client, "POST", "/api/redo"))
    assert redone["analysis"]["missionTime"] == 10


def test_settings_wrapped_body_and_nested_merge(client):
    response = api(client, "POST", "/api/analysis/settings",
                   json={"analysis": {"cutsets": {"maxOrder": 3}}})
    assert response.status_code == 200
    assert body(response)["analysis"]["cutsets"] == {"maxOrder": 3, "maxCount": 5000, "cutoff": 1e-15}


@pytest.mark.parametrize("payload, field", [
    ({"missionTime": 0}, "analysis.missionTime"),
    ({"cutsets": {"maxOrder": 99}}, "analysis.cutsets.maxOrder"),
    ({"mc": {"n": "many"}}, "analysis.mc.n"),
    ({"fmeaOccurrenceTable": {"11": 0.1}}, "analysis.fmeaOccurrenceTable.11"),
    ({"bogus": 1}, "analysis.bogus"),
])
def test_settings_reject_bad_values_without_an_undo_step(client, payload, field):
    response = api(client, "POST", "/api/analysis/settings", json=payload)
    assert response.status_code == 400
    error = body(response)["error"]
    assert error["code"] == "INVALID_FIELD"
    assert error["detail"]["field"] == field
    assert get_state().can_undo is False


def test_settings_need_a_body(client):
    assert api(client, "POST", "/api/analysis/settings", json={}).status_code == 400


def test_state_carries_analysis_and_capabilities(client):
    payload = body(api(client, "GET", "/api/state"))
    assert payload["analysis"]["missionTime"] == 8760
    assert payload["sessionWarnings"] == []
    assert isinstance(payload["capabilities"]["reportExport"], bool)
    assert isinstance(payload["capabilities"]["fmeaXlsx"], bool)


# ---- summary and stubs ---------------------------------------------------------------------


def test_summary(client):
    add(client, probability=0.5)
    add(client, probability=0.5)
    payload = body(api(client, "GET", "/api/analysis/summary"))
    assert payload["ok"] is True
    assert payload["treeWalk"] == 0.75
    assert payload["headline"] == 0.75
    assert payload["headlineMethod"] == "treeWalk"


@pytest.mark.parametrize("method, url", [
    ("GET", "/api/analysis/summary"),
    ("POST", "/api/analysis/cutsets"),
    ("POST", "/api/analysis/importance"),
    ("POST", "/api/analysis/uncertainty"),
])
def test_eta_mode_is_409(client, method, url):
    api(client, "POST", "/api/metadata", json={"mode": "ETA"})
    response = api(client, method, url, json={} if method == "POST" else None)
    assert response.status_code == 409
    assert body(response)["error"]["code"] == "MODE_UNSUPPORTED"
    ja = api(client, method, url + "?lang=ja", json={} if method == "POST" else None)
    assert any(ord(c) > 0x3000 for c in body(ja)["error"]["message"])


@pytest.mark.parametrize("url", [
    "/api/analysis/cutsets",
    "/api/analysis/importance",
    "/api/analysis/uncertainty",
    "/api/fmea/preview",
    "/api/fmea/import",
])
def test_stubs_are_501(client, url):
    response = api(client, "POST", url, json={})
    assert response.status_code == 501
    assert body(response)["error"]["code"] == "NOT_IMPLEMENTED"


def test_report_is_503_without_python_docx(client, monkeypatch):
    from fta_web.routes import report

    monkeypatch.setattr(report, "docx_available", lambda: False)
    response = api(client, "POST", "/api/report/docx", json={})
    assert response.status_code == 503
    error = body(response)["error"]
    assert error["code"] == "EXPORT_UNAVAILABLE"
    assert error["detail"]["format"] == "docx"
    assert "python-docx" in error["message"]
    ja = body(api(client, "POST", "/api/report/docx?lang=ja", json={}))["error"]["message"]
    assert "python-docx" in ja and "openpyxl" not in ja


def test_report_is_501_with_python_docx(client, monkeypatch):
    from fta_web.routes import report

    monkeypatch.setattr(report, "docx_available", lambda: True)
    response = api(client, "POST", "/api/report/docx", json={})
    assert response.status_code == 501


# ---- validate / session warnings ------------------------------------------------------------


def test_validate_is_empty_on_a_fresh_document(client):
    payload = body(api(client, "GET", "/api/analysis/validate"))
    assert payload["issues"] == []
    assert payload["counts"] == {"error": 0, "warning": 0, "info": 0}


def test_validate_reports_load_repairs_after_open(client, tmp_path):
    path = tmp_path / "dups.json"
    path.write_text(json.dumps({"title": "t", "date": "d", "mode": "FTA", "tree": {
        "id": "TOP", "name": "top", "children": [
            {"id": "x", "name": "a", "probability": 0.1},
            {"id": "x", "name": "b", "probability": 0.2},
        ]}}), encoding="utf-8")
    opened = api(client, "POST", "/api/file/open", json={"path": str(path)})
    assert opened.status_code == 200, body(opened)
    assert len(body(opened)["sessionWarnings"]) == 2

    payload = body(api(client, "GET", "/api/analysis/validate"))
    codes = [issue["code"] for issue in payload["issues"]]
    assert codes == ["LOAD_REPAIR", "LOAD_REPAIR"]
    assert {issue["nodeId"] for issue in payload["issues"]} == {"root", "x_dup2"}
    for issue in payload["issues"]:
        assert set(issue) == {"severity", "code", "nodeId", "message", "params"}
    assert payload["counts"]["warning"] == 2

    # A new document clears them.
    api(client, "POST", "/api/new", json={"force": True})
    assert body(api(client, "GET", "/api/analysis/validate"))["issues"] == []


def test_validate_reports_links_removed_by_a_delete(client):
    a = add(client, probability=0.1)
    b = add(client, probability=0.2, links=[{"target_id": a, "relation": "OR"}])
    deleted = body(api(client, "DELETE", "/api/nodes/%s" % a))
    assert deleted["removedLinks"] == [{"nodeId": b, "targetId": a, "relation": "OR"}]
    assert [w["code"] for w in deleted["sessionWarnings"]] == ["LINKS_REMOVED"]

    issues = body(api(client, "GET", "/api/analysis/validate"))["issues"]
    assert len(issues) == 1
    assert issues[0]["code"] == "LINKS_REMOVED"
    assert issues[0]["nodeId"] == b
    assert issues[0]["params"]["targetId"] == a

    # Session warnings are not document state: undo does not remove them.
    api(client, "POST", "/api/undo")
    assert len(body(api(client, "GET", "/api/analysis/validate"))["issues"]) == 1


def test_session_warnings_helpers():
    issues = state_module.load_warning_issues([
        {"kind": "duplicate_id", "old_id": "x", "new_id": "x_dup2", "message": "m"},
    ])
    assert issues == [{"severity": "warning", "code": "LOAD_REPAIR", "nodeId": "x_dup2",
                       "message": "m", "params": {"kind": "duplicate_id", "old_id": "x",
                                                  "new_id": "x_dup2", "message": "m"}}]


# ---- file round trip through the API --------------------------------------------------------


def test_save_and_open_keep_analysis(client, tmp_path):
    api(client, "POST", "/api/analysis/settings", json={"missionTime": 24})
    target = tmp_path / "saved.json"
    assert api(client, "POST", "/api/file/save-as", json={"path": str(target)}).status_code == 200
    assert json.loads(target.read_text(encoding="utf-8"))["analysis"]["missionTime"] == 24
    api(client, "POST", "/api/new", json={"force": True})
    assert get_state().core.analysis["missionTime"] == 8760
    opened = body(api(client, "POST", "/api/file/open", json={"path": str(target)}))
    assert opened["analysis"]["missionTime"] == 24


# ---- /api/dot parameters ----------------------------------------------------------------------


def test_dot_accepts_the_new_parameters(client):
    plain = body(api(client, "GET", "/api/dot"))
    assert plain["idMap"].get("root") == "root"  # every DOT node name -> node id
    assert plain["style"] == "compact" and plain["rankdir"] == "LR" and plain["sigFigs"] == 3
    styled = body(api(client, "GET", "/api/dot?style=symbols&rankdir=tb&sigFigs=5"))
    assert styled["style"] == "symbols" and styled["rankdir"] == "TB" and styled["sigFigs"] == 5
    assert "rankdir=TB;" in styled["dot"] and "fta-box" in styled["dot"]


@pytest.mark.parametrize("query", ["style=fancy", "rankdir=RL"])
def test_dot_rejects_bad_parameters(client, query):
    response = api(client, "GET", "/api/dot?" + query)
    assert response.status_code == 400
    assert body(response)["error"]["code"] == "INVALID_FIELD"


def test_create_app_registers_the_new_blueprints():
    from fta_web.app import create_app

    rules = {rule.rule for rule in create_app().url_map.iter_rules()}
    assert {
        "/api/analysis/settings", "/api/analysis/summary", "/api/analysis/cutsets",
        "/api/analysis/importance", "/api/analysis/uncertainty",
        "/api/analysis/validate", "/api/report/docx", "/api/fmea/preview",
        "/api/fmea/import",
    } <= rules


# ---- AI full-tree update merge-back -------------------------------------------------------------


def test_ai_update_merges_the_new_keys_back(tmp_path, monkeypatch):
    import flask

    from AI_agent_handler import AICredentialManager
    from ai_providers import AIProviderFactory

    from fta_web import ai_bridge
    from fta_web.routes.ai import ai_bp
    from fta_web.routes.tree import tree_bp

    directory = tmp_path / "fta_editor_home"
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_DIR", directory)
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_FILE", directory / "ai_credentials.json")
    reset_state()
    ai_bridge.reset_handler()
    app = flask.Flask(__name__)
    app.register_blueprint(tree_bp)
    app.register_blueprint(ai_bp)
    app.config.update(TESTING=True)
    provider = AIProviderFactory.get_provider("OpenAI")
    monkeypatch.setattr(provider, "test_connection", lambda *a, **k: (True, "ok"))

    with app.test_client() as client:
        assert client.post("/api/ai/credentials",
                           json={"provider": "OpenAI", "apiKey": "sk-test-key-0000"}).status_code == 200
        nid = add(client, probability=0.5,
                  quant={"model": "rate", "lambda": 1e-4, "T": 10}, trace={"owner": "me"})
        live = get_state().core.get_data()
        rewritten = {
            "id": "root", "name": live["name"], "type": "Root", "probability": 1.0,
            "logicGate": "OR", "notes": "", "links": [],
            "children": [{"id": nid, "name": "Renamed by AI", "type": "Event",
                          "probability": 0.5, "logicGate": "OR", "notes": "",
                          "links": [], "children": []}],
        }
        monkeypatch.setattr(provider, "send_message",
                            lambda *a, **k: (json.dumps(rewritten), None))
        response = client.post("/api/ai/update", json={})
        assert response.status_code == 200, body(response)
        assert body(response)["mergedFields"] == 2
        node = get_state().core.find_node_by_id(nid)
        assert node["name"] == "Renamed by AI"
        assert node["quant"] == {"model": "rate", "lambda": 1e-4, "T": 10.0}
        assert node["trace"] == {"owner": "me"}
        assert node["probability"] == pytest.approx(1 - 2.718281828459045 ** -1e-3, rel=1e-9)
