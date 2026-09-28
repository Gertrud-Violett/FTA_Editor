"""
``GET /api/analysis/validate`` end to end: lint rules on the live document,
both modes, session warnings from open and delete, and a fix clearing an issue.
"""
import json

import pytest

from fta_web.state import get_state, reset_state

pytest.importorskip("flask")


@pytest.fixture
def client(tmp_path):
    """Blueprints on a bare app through the ``fta_web`` package (see
    test_analysis_routes.py for why not ``create_app()``)."""
    import flask

    from fta_web.routes.files import files_bp
    from fta_web.routes.tree import tree_bp
    from fta_web.routes.validate import validate_bp

    reset_state()
    app = flask.Flask(__name__)
    for bp in (tree_bp, files_bp, validate_bp):
        app.register_blueprint(bp)
    app.config.update(TESTING=True)
    get_state().fs_root = tmp_path
    with app.test_client() as test_client:
        yield test_client


def body(response):
    return json.loads(response.get_data(as_text=True))


def add(client, parent="root", **fields):
    fields.setdefault("name", "Event")
    response = client.post("/api/nodes", json=dict(fields, parentId=parent))
    assert response.status_code == 200, body(response)
    return body(response)["nodeId"]


def validate(client):
    response = client.get("/api/analysis/validate")
    assert response.status_code == 200, body(response)
    return body(response)


def test_fresh_document_is_clean(client):
    payload = validate(client)
    assert payload["issues"] == []
    assert payload["counts"] == {"error": 0, "warning": 0, "info": 0}
    assert payload["mode"] == "FTA"


def test_reports_rules_with_counts_and_fixing_clears_them(client):
    a = add(client, probability=1.0)
    b = add(client, probability=0.2, links=[{"target_id": "root", "relation": "OR"}])
    payload = validate(client)
    found = {(i["code"], i["nodeId"]) for i in payload["issues"]}
    assert ("DEFAULT_PROBABILITY", a) in found
    assert ("CYCLIC_LINK", b) in found
    assert payload["counts"]["warning"] == len(payload["issues"])
    for issue in payload["issues"]:
        assert set(issue) == {"severity", "code", "nodeId", "message", "params"}

    client.patch("/api/nodes/%s" % a, json={"probability": 0.01})
    client.patch("/api/nodes/%s" % b, json={"links": []})
    assert validate(client)["issues"] == []


def test_errors_sort_first(client):
    add(client, probability=1.0)
    add(client, probability=0.1, links=[{"target_id": "ghost", "relation": "OR"}])
    issues = validate(client)["issues"]
    assert [i["severity"] for i in issues] == ["error", "warning"]
    assert issues[0]["code"] == "DANGLING_LINK"


def test_eta_mode_has_its_own_rules(client):
    add(client, probability=0.4, links=[{"target_id": "ghost", "relation": "OR"}])
    add(client, probability=0.4)
    client.post("/api/metadata", json={"mode": "ETA"})
    payload = validate(client)
    assert payload["mode"] == "ETA"
    assert [i["code"] for i in payload["issues"]] == ["ETA_BRANCH_SUM"]
    assert payload["issues"][0]["params"]["sum"] == pytest.approx(0.8)


def test_open_with_duplicate_ids_reports_load_repairs(client, tmp_path):
    path = tmp_path / "dups.json"
    path.write_text(json.dumps({"title": "t", "date": "d", "mode": "FTA", "tree": {
        "id": "root", "name": "top", "children": [
            {"id": "x", "name": "a", "probability": 0.1},
            {"id": "x", "name": "b", "probability": 1.0},
        ]}}), encoding="utf-8")
    opened = client.post("/api/file/open", json={"path": str(path)})
    assert opened.status_code == 200, body(opened)
    issues = validate(client)["issues"]
    assert [(i["code"], i["nodeId"]) for i in issues] == [
        ("DEFAULT_PROBABILITY", "x_dup2"),
        ("LOAD_REPAIR", "x_dup2"),
    ]
    assert issues[1]["params"]["kind"] == "duplicate_id"


def test_delete_with_incoming_links_reports_links_removed(client):
    a = add(client, probability=0.1)
    b = add(client, probability=0.2, links=[{"target_id": a, "relation": "AND"}])
    add(client, probability=0.3)
    client.delete("/api/nodes/%s" % a)
    issues = validate(client)["issues"]
    assert [(i["code"], i["nodeId"]) for i in issues] == [("LINKS_REMOVED", b)]
    assert issues[0]["params"]["targetId"] == a


def test_does_not_modify_the_document(client):
    g = add(client, probability=0.7, logicGate="AND")
    add(client, parent=g, probability=0.1)
    before = json.dumps(get_state().core.get_data(), sort_keys=True)
    dirty = get_state().dirty
    validate(client)
    assert json.dumps(get_state().core.get_data(), sort_keys=True) == before
    assert get_state().dirty == dirty
