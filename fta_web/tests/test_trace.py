"""
Traceability fields (1.7 workstream C): the ``trace`` block the Traceability
tab edits through ``PATCH /api/nodes/<id>`` survives save/load and undo.
"""
import json

import pytest

from fta_web.state import get_state, reset_state

pytest.importorskip("flask")


@pytest.fixture
def client(tmp_path):
    import flask

    from fta_web.routes.files import files_bp
    from fta_web.routes.fmea import fmea_bp
    from fta_web.routes.tree import tree_bp

    reset_state()
    app = flask.Flask(__name__)
    for bp in (tree_bp, files_bp, fmea_bp):
        app.register_blueprint(bp)
    app.config.update(TESTING=True)
    get_state().fs_root = tmp_path
    with app.test_client() as test_client:
        yield test_client


def body(response):
    return json.loads(response.get_data(as_text=True))


def add(client, **fields):
    fields.setdefault("name", "Event")
    response = client.post("/api/nodes", json=dict(fields, parentId="root"))
    assert response.status_code == 200, body(response)
    return body(response)["nodeId"]


def patch(client, node_id, trace):
    response = client.patch("/api/nodes/" + node_id, json={"trace": trace})
    assert response.status_code == 200, body(response)
    return body(response)["node"]["trace"]


def test_field_by_field_edits_merge(client):
    nid = add(client)
    assert patch(client, nid, {"requirementId": "REQ-1"}) == {"requirementId": "REQ-1"}
    assert patch(client, nid, {"owner": "Alice"}) == {"requirementId": "REQ-1", "owner": "Alice"}
    assert patch(client, nid, {"tags": [" brake ", "asil-d", "brake", ""]})["tags"] == [
        "brake", "asil-d"]
    assert patch(client, nid, {"status": "Approved"})["status"] == "approved"
    # Clearing a field (the tab sends null for an emptied cell) removes it.
    assert "owner" not in patch(client, nid, {"owner": None})


def test_invalid_trace_values(client):
    nid = add(client)
    for bad in ({"status": "done"}, {"tags": "a,b"}, {"bogus": "x"}, {"owner": 3}):
        response = client.patch("/api/nodes/" + nid, json={"trace": bad})
        assert response.status_code == 400
        assert body(response)["error"]["code"] == "INVALID_FIELD"


def test_trace_round_trips_through_save_and_load(client, tmp_path):
    nid = add(client)
    trace = {"requirementId": "REQ-7", "testRef": "TC-3", "owner": "山田",
             "status": "reviewed", "evidence": "https://example.com/e/1",
             "tags": ["brake", "安全"]}
    assert patch(client, nid, trace) == trace
    target = tmp_path / "doc.json"
    response = client.post("/api/file/save-as", json={"path": str(target)})
    assert response.status_code == 200, body(response)
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert on_disk["tree"]["children"][0]["trace"] == trace

    reset_state()
    get_state().fs_root = tmp_path
    response = client.post("/api/file/open", json={"path": str(target)})
    assert response.status_code == 200, body(response)
    assert body(client.get("/api/nodes/" + nid))["node"]["trace"] == trace


def test_trace_edit_is_one_undo_step(client):
    nid = add(client)
    patch(client, nid, {"requirementId": "REQ-1"})
    patch(client, nid, {"requirementId": "REQ-2"})
    client.post("/api/undo")
    assert get_state().core.find_node_by_id(nid)["trace"] == {"requirementId": "REQ-1"}
