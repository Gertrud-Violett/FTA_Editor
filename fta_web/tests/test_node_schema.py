"""
Tests for fta_web/node_schema.py and the 1.7 node keys on the tree API
(``POST /api/nodes``, ``PATCH /api/nodes/<id>``, ``GET /api/nodes/<id>``).
"""
import json

import pytest

from fta_web import node_schema
from fta_web.errors import ApiError
from fta_web.state import get_state, reset_state

pytest.importorskip("flask")


@pytest.fixture
def client():
    import flask

    from fta_web.routes.tree import tree_bp

    reset_state()
    app = flask.Flask(__name__)
    app.register_blueprint(tree_bp)
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


def body(response):
    return json.loads(response.get_data(as_text=True))


def add(client, **fields):
    fields.setdefault("parentId", "root")
    fields.setdefault("name", "Event")
    response = client.post("/api/nodes", json=fields)
    assert response.status_code == 200, body(response)
    return body(response)["nodeId"]


def patch(client, node_id, **fields):
    return client.patch("/api/nodes/%s" % node_id, json=fields)


def stored(node_id):
    return get_state().core.find_node_by_id(node_id)


# ---- pure helpers -------------------------------------------------------------------


@pytest.mark.parametrize("gate_type, projected", [
    ("AND", "AND"), ("INHIBIT", "AND"), ("PAND", "AND"),
    ("OR", "OR"), ("KOFN", "OR"), ("XOR", "OR"), ("TRANSFER", "OR"),
    ("kofn", "OR"), ("pand", "AND"), (None, "OR"), ("bogus", "OR"),
])
def test_project_logic_gate(gate_type, projected):
    assert node_schema.project_logic_gate(gate_type) == projected


def test_merge_partial_null_removes_and_dicts_merge():
    existing = {"model": "rate", "lambda": 1e-6, "unc": {"dist": "lognormal", "ef": 3}}
    merged = node_schema.merge_partial(existing, {"lambda": None, "T": 10, "unc": {"ef": 10}})
    assert merged == {"model": "rate", "T": 10, "unc": {"dist": "lognormal", "ef": 10}}
    assert existing["lambda"] == 1e-6  # not mutated
    assert node_schema.merge_partial(merged, {"unc": {"dist": None, "ef": None}}) == {
        "model": "rate", "T": 10,
    }


@pytest.mark.parametrize("validator, value", [
    (node_schema.validate_gate_type, "NOT"),
    (node_schema.validate_gate_type, 3),
    (node_schema.validate_k, 0),
    (node_schema.validate_k, True),
    (node_schema.validate_k, 1.5),
    (node_schema.validate_event_kind, "weird"),
    (node_schema.validate_house_state, "true"),
    (node_schema.validate_transfer_to, {"id": 1}),
    (node_schema.validate_quant, {"model": "weibull"}),
    (node_schema.validate_quant, {"lambda": -1}),
    (node_schema.validate_quant, {"T": 0}),
    (node_schema.validate_quant, {"lambda": float("nan")}),
    (node_schema.validate_quant, {"bogus": 1}),
    (node_schema.validate_quant, {"unc": {"dist": "normal"}}),
    (node_schema.validate_quant, {"unc": {"ef": 0.5}}),
    (node_schema.validate_quant, "rate"),
    (node_schema.validate_trace, {"status": "done"}),
    (node_schema.validate_trace, {"tags": "a,b"}),
    (node_schema.validate_trace, {"owner": 5}),
    (node_schema.validate_fmea, {"severity": 11}),
    (node_schema.validate_fmea, {"occurrence": 0}),
    (node_schema.validate_fmea, {"rpn": -1}),
    (node_schema.validate_fmea, {"mode": 3}),
])
def test_validators_reject(validator, value):
    with pytest.raises(ApiError) as info:
        validator(value)
    assert info.value.code == "INVALID_FIELD"
    assert info.value.status == 400
    assert "field" in info.value.detail


def test_validators_normalise():
    assert node_schema.validate_gate_type("kofn") == "KOFN"
    assert node_schema.validate_gate_type("") is None
    assert node_schema.validate_k(2.0) == 2
    assert node_schema.validate_event_kind("House") == "house"
    assert node_schema.validate_transfer_to(12) == "12"
    assert node_schema.validate_quant({"model": "RATE", "lambda": 1}) == {"model": "rate", "lambda": 1.0}
    assert node_schema.validate_trace({"tags": [" a ", "a", "", "b"]}) == {"tags": ["a", "b"]}
    assert node_schema.validate_fmea({"id": 7, "severity": 3.0}) == {"id": "7", "severity": 3}


def test_merge_back_node_keys():
    before = {"id": "root", "logicGate": "OR", "gateType": "KOFN", "k": 2, "children": [
        {"id": "a", "quant": {"model": "rate", "lambda": 1e-6}, "trace": {"owner": "x"}},
        {"id": "b", "gateType": "PAND", "logicGate": "AND", "children": []},
    ]}
    after = {"id": "root", "logicGate": "OR", "children": [
        {"id": "a", "trace": {"owner": "AI"}},
        {"id": "b", "logicGate": "OR", "children": []},  # the AI changed AND->OR
        {"id": "c"},
    ]}
    restored = node_schema.merge_back_node_keys(before, after)
    assert restored == 3  # root gateType + k, a.quant
    assert after["gateType"] == "KOFN" and after["k"] == 2
    assert after["children"][0]["quant"] == {"model": "rate", "lambda": 1e-6}
    assert after["children"][0]["trace"] == {"owner": "AI"}  # the AI's own value wins
    assert "gateType" not in after["children"][1]


# ---- the API ------------------------------------------------------------------------------


def test_patch_accepts_every_new_key(client):
    nid = add(client)
    response = patch(
        client, nid,
        gateType="KOFN", k=2, eventKind="basic", houseState=False, transferTo="root",
        quant={"model": "rate", "lambda": 1e-6, "T": 100, "source": "handbook"},
        trace={"requirementId": "REQ-1", "status": "draft", "tags": ["x"]},
        fmea={"id": "F-1", "severity": 5, "occurrence": 3, "detection": 2, "rpn": 30},
    )
    assert response.status_code == 200, body(response)
    node = stored(nid)
    assert node["gateType"] == "KOFN" and node["logicGate"] == "OR"
    assert node["k"] == 2
    assert node["quant"]["lambda"] == 1e-6
    assert node["trace"]["requirementId"] == "REQ-1"
    assert node["fmea"]["rpn"] == 30

    view = body(response)["node"]
    for key in node_schema.NODE_KEYS:
        assert key in view
    assert set(view["quantDerived"]) >= {"q", "formula", "formulaKey", "params", "warnings"}
    assert view["quantDerived"]["q"] == pytest.approx(1e-4, rel=1e-3)
    assert node["probability"] == pytest.approx(view["quantDerived"]["q"])


def test_node_view_has_null_new_keys_on_a_legacy_node(client):
    nid = add(client, probability=0.2)
    view = body(client.get("/api/nodes/%s" % nid))["node"]
    for key in node_schema.NODE_KEYS:
        assert view[key] is None
    assert view["quantDerived"]["model"] == "fixed"
    assert view["quantDerived"]["q"] == 0.2


@pytest.mark.parametrize("fields", [
    {"gateType": "NOT"},
    {"k": 0},
    {"eventKind": "x"},
    {"houseState": 1},
    {"quant": {"model": "nope"}},
    {"quant": {"lambda": "fast"}},
    {"trace": {"status": "final"}},
    {"fmea": {"severity": 0}},
    {"logicGate": "XOR"},  # logicGate stays AND/OR only
    {"logicGate": "NOT"},
    {"gateType": "PAND", "logicGate": "OR"},  # contradicts the projection
    {"bogus": 1},
])
def test_patch_rejects(client, fields):
    nid = add(client)
    before = json.dumps(stored(nid), sort_keys=True)
    response = patch(client, nid, **fields)
    assert response.status_code == 400
    assert body(response)["error"]["code"] == "INVALID_FIELD"
    assert json.dumps(stored(nid), sort_keys=True) == before


def test_gate_type_projection_and_logic_gate_sync(client):
    nid = add(client)
    assert body(patch(client, nid, gateType="PAND"))["node"]["logicGate"] == "AND"
    assert stored(nid)["gateType"] == "PAND"

    # Setting logicGate directly on a node with a gateType keeps them in step.
    patch(client, nid, logicGate="OR")
    assert stored(nid)["gateType"] == "OR" and stored(nid)["logicGate"] == "OR"

    # Removing gateType leaves logicGate alone.
    patch(client, nid, gateType=None)
    assert "gateType" not in stored(nid)
    assert stored(nid)["logicGate"] == "OR"

    # A legacy node given only a logicGate does not grow a gateType.
    patch(client, nid, logicGate="AND")
    assert "gateType" not in stored(nid)


def test_partial_merge_and_null_removal(client):
    nid = add(client)
    patch(client, nid, quant={"model": "rate", "lambda": 1e-5, "unc": {"dist": "lognormal", "ef": 3}})
    patch(client, nid, quant={"T": 50, "unc": {"ef": 10}})
    assert stored(nid)["quant"] == {
        "model": "rate", "lambda": 1e-5, "T": 50.0, "unc": {"dist": "lognormal", "ef": 10.0},
    }
    patch(client, nid, quant={"T": None, "unc": None})
    assert stored(nid)["quant"] == {"model": "rate", "lambda": 1e-5}
    patch(client, nid, quant=None)
    assert "quant" not in stored(nid)

    patch(client, nid, trace={"owner": "me"})
    patch(client, nid, trace={"owner": None})
    assert "trace" not in stored(nid)  # emptied -> removed

    patch(client, nid, k=3)
    patch(client, nid, k=None)
    assert "k" not in stored(nid)


def test_create_accepts_the_new_keys(client):
    response = client.post("/api/nodes", json={
        "parentId": "root", "name": "Voting", "gateType": "KOFN", "k": 2,
        "quant": {"model": "fixed", "source": None},
        "fmea": {"id": "F9"},
    })
    assert response.status_code == 200, body(response)
    node = stored(body(response)["nodeId"])
    assert node["gateType"] == "KOFN" and node["logicGate"] == "OR" and node["k"] == 2
    assert node["quant"] == {"model": "fixed"}
    assert node["fmea"] == {"id": "F9"}


def test_create_rejects_bad_new_keys(client):
    response = client.post("/api/nodes", json={"parentId": "root", "name": "x", "k": -1})
    assert response.status_code == 400
    assert body(response)["error"]["detail"]["field"] == "k"


def test_a_patch_is_one_undo_step(client):
    nid = add(client)
    patch(client, nid, quant={"model": "rate", "lambda": 1e-3, "T": 10})
    assert "quant" in stored(nid)
    assert client.post("/api/undo").status_code == 200
    assert "quant" not in stored(nid)


def test_house_event_through_the_api(client):
    a = add(client, probability=0.4)
    h = add(client, probability=0.9, eventKind="house", houseState=True)
    patch(client, "root", logicGate="AND")
    assert get_state().core.get_data()["calculatedProbability"] == 0.4
    payload = body(patch(client, h, houseState=False))
    assert payload["tree"]["calculatedProbability"] == 0.0
    assert a
