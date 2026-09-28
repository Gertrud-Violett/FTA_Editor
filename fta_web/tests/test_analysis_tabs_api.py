"""
Route tests for the workstream-A endpoints: /api/analysis/{summary, cutsets,
importance, uncertainty}. Same bare-app pattern as test_analysis_routes.py.
"""
import json

import pytest

from fta_web.state import get_state, reset_state

pytest.importorskip("flask")


@pytest.fixture
def client(tmp_path):
    import flask

    from fta_web.routes.analysis import analysis_bp
    from fta_web.routes.tree import tree_bp

    reset_state()
    app = flask.Flask(__name__)
    for bp in (tree_bp, analysis_bp):
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


def build(client):
    """root(OR) -> g1(AND: A, B), g2(AND: A via transfer, C)."""
    client.patch("/api/nodes/root", json={"logicGate": "OR"})
    g1 = add(client, name="g1", logicGate="AND")
    g2 = add(client, name="g2", logicGate="AND")
    a = add(client, g1, name="A", probability=0.1,
            quant={"model": "fixed", "unc": {"dist": "lognormal", "median": 0.1, "ef": 3}})
    b = add(client, g1, name="B", probability=0.2)
    t = add(client, g2, name="T")
    assert client.patch("/api/nodes/%s" % t,
                        json={"gateType": "TRANSFER", "transferTo": a}).status_code == 200
    c = add(client, g2, name="C", probability=0.3)
    return {"A": a, "B": b, "C": c, "g1": g1, "g2": g2, "T": t}


def test_summary_uses_mcub_with_a_repeated_event(client):
    ids = build(client)
    payload = body(client.get("/api/analysis/summary"))
    assert payload["ok"] is True
    assert payload["headlineMethod"] == "mcub"
    assert payload["repeatedEvents"] == [{"id": ids["A"], "name": "A"}]
    assert payload["mcub"] == pytest.approx(1 - 0.98 * 0.97)
    assert payload["rareEvent"] == pytest.approx(0.05)
    assert payload["truncated"] is False
    assert set(payload) >= {"treeWalk", "headline", "nonCoherent", "approximations", "elapsedMs"}


def test_cutsets_endpoint(client):
    ids = build(client)
    payload = body(client.post("/api/analysis/cutsets", json={}))
    assert payload["ok"] is True
    assert payload["total"] == payload["returned"] == 2
    events = [[e["id"] for e in cs["events"]] for cs in payload["cutSets"]]
    assert events == [sorted([ids["A"], ids["C"]], key=lambda i: {ids["A"]: "A", ids["C"]: "C"}[i]),
                      sorted([ids["A"], ids["B"]], key=lambda i: {ids["A"]: "A", ids["B"]: "B"}[i])]
    assert payload["cutSets"][0]["share"] == pytest.approx(0.6)
    assert payload["limits"] == {"maxOrder": 6, "maxCount": 5000, "cutoff": 1e-15}

    limited = body(client.post("/api/analysis/cutsets", json={"limit": 1}))
    assert limited["returned"] == 1 and limited["total"] == 2
    assert limited["mcub"] == payload["mcub"]

    order1 = body(client.post("/api/analysis/cutsets", json={"maxOrder": 1}))
    assert order1["total"] == 0 and order1["truncatedBy"] == ["order"]


@pytest.mark.parametrize("payload, field", [
    ({"maxOrder": 0}, "maxOrder"),
    ({"maxCount": "x"}, "maxCount"),
    ({"cutoff": 1.5}, "cutoff"),
    ({"limit": -1}, "limit"),
])
def test_cutsets_reject_bad_limits(client, payload, field):
    response = client.post("/api/analysis/cutsets", json=payload)
    assert response.status_code == 400
    error = body(response)["error"]
    assert error["code"] == "INVALID_FIELD" and error["detail"]["field"] == field


def test_too_large_voting_gate_is_422(client):
    v = add(client, name="vote")
    client.patch("/api/nodes/%s" % v, json={"gateType": "KOFN", "k": 10})
    for i in range(30):
        add(client, v, name="e%d" % i, probability=0.01)
    response = client.post("/api/analysis/cutsets", json={})
    assert response.status_code == 422
    error = body(response)["error"]
    assert error["code"] == "ANALYSIS_TOO_LARGE"
    assert error["detail"]["reason"] == "kofn" and error["detail"]["nodeId"] == v
    # The headline survives: tree walk, flagged truncated.
    summary = body(client.get("/api/analysis/summary"))
    assert summary["truncated"] is True and summary["headlineMethod"] == "treeWalk"


def test_importance_endpoint(client):
    ids = build(client)
    payload = body(client.post("/api/analysis/importance", json={}))
    assert payload["ok"] is True and payload["basis"] == "mcub"
    assert payload["topValue"] == pytest.approx(1 - 0.98 * 0.97)
    first = payload["events"][0]
    assert first["id"] == ids["A"] and first["fv"] == pytest.approx(1.0)
    assert first["rrw"] is None and first["rrwInfinite"] is True
    assert set(first) == {"id", "name", "q", "fv", "birnbaum", "raw", "rrw",
                          "rrwInfinite", "cutSetCount"}
    assert payload["cutSetTotal"] == 2 and payload["truncated"] is False


def test_uncertainty_endpoint(client):
    build(client)
    payload = body(client.post("/api/analysis/uncertainty", json={"n": 800, "seed": 7}))
    assert payload["ok"] is True
    assert payload["completed"] == payload["requested"] == 800
    assert payload["seed"] == 7 and payload["method"] == "cutsets"
    assert len(payload["histogram"]["counts"]) == 40
    again = body(client.post("/api/analysis/uncertainty", json={"n": 800, "seed": 7}))
    assert again["mean"] == payload["mean"]
    # n and seed default from analysis.mc
    client.post("/api/analysis/settings", json={"mc": {"n": 300, "seed": 3}})
    defaulted = body(client.post("/api/analysis/uncertainty", json={}))
    assert defaulted["requested"] == 300 and defaulted["seed"] == 3


@pytest.mark.parametrize("payload, field", [
    ({"n": 100001}, "n"),
    ({"n": 0}, "n"),
    ({"seed": -1}, "seed"),
    ({"timeLimit": 61}, "timeLimit"),
    ({"timeLimit": 0}, "timeLimit"),
    ({"bins": 0}, "bins"),
])
def test_uncertainty_rejects_bad_parameters(client, payload, field):
    response = client.post("/api/analysis/uncertainty", json=payload)
    assert response.status_code == 400
    assert body(response)["error"]["detail"]["field"] == field


def test_uncertainty_is_one_at_a_time(client):
    from fta_web.routes import analysis

    assert analysis._mc_lock.acquire(blocking=False)
    try:
        response = client.post("/api/analysis/uncertainty", json={"n": 10})
        assert response.status_code == 409
        assert body(response)["error"]["code"] == "BUSY"
    finally:
        analysis._mc_lock.release()
    assert client.post("/api/analysis/uncertainty", json={"n": 10}).status_code == 200


def test_computations_do_not_touch_the_document(client):
    build(client)
    state = get_state()
    before = json.dumps(state.core.get_data(), sort_keys=True)
    undo = state.can_undo
    for url in ("/api/analysis/cutsets", "/api/analysis/importance",
                "/api/analysis/uncertainty"):
        assert client.post(url, json={"n": 50} if "uncertainty" in url else {}).status_code == 200
    assert client.get("/api/analysis/summary").status_code == 200
    assert json.dumps(state.core.get_data(), sort_keys=True) == before
    assert state.can_undo == undo


@pytest.mark.parametrize("method, url", [
    ("GET", "/api/analysis/summary"),
    ("POST", "/api/analysis/cutsets"),
    ("POST", "/api/analysis/importance"),
    ("POST", "/api/analysis/uncertainty"),
])
def test_eta_mode_is_409(client, method, url):
    client.post("/api/metadata", json={"mode": "ETA"})
    response = client.open(url, method=method, json={} if method == "POST" else None)
    assert response.status_code == 409
    assert body(response)["error"]["code"] == "MODE_UNSUPPORTED"
