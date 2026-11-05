"""Unit tests of the CCF reporting pieces added by F2 T3 (FN-33, FN-37, FN-28).

The acceptance tests in ``acceptance/ccf`` judge the lint table end to end;
these pin the small contracts around it: the session-only ``_ccf*`` keys never
reach an API payload, the summary keys exist only for a document with groups,
and the reserved-id finding keeps the kind ``id`` of DESIGN section 4.
"""
import json

import pytest

from fta_web import ccf, ccf_text


def leaf(node_id, q=1e-3):
    return {"id": node_id, "name": "Pump " + node_id, "type": "Event", "logicGate": "OR",
            "probability": q, "notes": "", "links": [], "children": []}


def tree(*children):
    return {"id": "root", "name": "Top", "type": "Root", "logicGate": "AND", "probability": 1.0,
            "notes": "", "links": [], "children": list(children)}


def group(gid="g1", members=("A", "B"), **over):
    out = ccf.make_group(gid, "Feed " + gid, 0.1, members, "")
    out.update(over)
    return out


# ---- the private session keys stay out of API payloads -------------------------------


def test_public_analysis_drops_private_keys_and_copies():
    analysis = {"missionTime": 10.0, "ccfGroups": [group()], "_ccfRenamed": {"g1": ["A"]},
                "_ccfOther": 1}
    out = ccf.public_analysis(analysis)
    assert out == {"missionTime": 10.0, "ccfGroups": analysis["ccfGroups"]}
    assert out["ccfGroups"] is not analysis["ccfGroups"]
    assert "_ccfRenamed" in analysis  # the engine state keeps it
    assert ccf.public_analysis(None) is None


@pytest.fixture
def api(tmp_path):
    flask = pytest.importorskip("flask")
    from fta_web.routes.ccf import ccf_bp
    from fta_web.routes.tree import tree_bp
    from fta_web.state import get_state, reset_state

    reset_state()
    app = flask.Flask(__name__)
    app.register_blueprint(tree_bp)
    app.register_blueprint(ccf_bp)
    app.config.update(TESTING=True)
    state = get_state()
    state.fs_root = tmp_path
    state.core.set_data(tree(leaf("A"), leaf("B")))
    state.core.analysis["ccfGroups"] = [group()]
    state.core.analysis["_ccfRenamed"] = {"g1": ["A"]}
    with app.test_client() as client:
        yield client, state
    reset_state()


def _json(response):
    return json.loads(response.get_data().decode("utf-8"))


def test_no_api_payload_carries_a_private_ccf_key(api):
    client, state = api
    seen = [
        _json(client.get("/api/state"))["analysis"],
        _json(client.patch("/api/ccf/groups/g1", json={"name": "Renamed"}))["analysis"],
        _json(client.post("/api/ccf/groups", json={
            "name": "Second", "model": "beta", "beta": 0.2, "members": ["A", "B"]}))["analysis"],
        _json(client.delete("/api/ccf/groups/g2"))["analysis"],
    ]
    for analysis in seen:
        assert "ccfGroups" in analysis
        assert [k for k in analysis if k.startswith("_ccf")] == []
    # the engine state still has the flag (CCF_MEMBER_RENAMED needs it) ...
    assert state.core.analysis["_ccfRenamed"] == {"g1": ["A"]}


def test_a_snapshot_keeps_the_private_key_for_undo(api):
    _client, state = api
    assert state.snapshot()["analysis"]["_ccfRenamed"] == {"g1": ["A"]}


def test_an_empty_patch_names_no_field_in_its_detail(api):
    client, _state = api
    response = client.patch("/api/ccf/groups/g1", json={})
    assert response.status_code == 400
    error = _json(response)["error"]
    assert error["code"] == "INVALID_FIELD" and error["message"] == "No group fields to update."
    assert error["detail"] == {"field": None}


# ---- the summary keys (FN-37, FN-28) ---------------------------------------------------


def test_summary_fields_are_absent_without_groups():
    assert ccf.summary_fields(tree(leaf("A")), {}) == {}
    assert ccf.summary_fields(tree(leaf("A")), None, "error") == {}


def test_summary_fields_report_applied_and_not_applied_groups():
    analysis = {"ccfGroups": [group(), group("g2", ["C", "ghost"])]}
    fields = ccf.summary_fields(tree(leaf("A"), leaf("B"), leaf("C")), analysis)
    assert fields["ccfIncomplete"] is False and "ccfIncompleteReason" not in fields
    block = fields["ccf"]
    assert [g["id"] for g in block["applied"]] == ["g1"]
    assert block["notApplied"] == [{"id": "g2", "name": "Feed g2",
                                    "code": "CCF_MEMBER_NOT_BASIC",
                                    "reason": '"ghost" is not in the tree'}]
    assert block["note"] == ccf_text.text("en", "note")


@pytest.mark.parametrize("reason", ccf.INCOMPLETE_REASONS)
def test_cut_sets_that_fail_make_the_summary_incomplete_only_with_an_applied_group(reason):
    both = {"ccfGroups": [group(), group("g2", ["C", "D"], beta="abc")]}
    fields = ccf.summary_fields(tree(leaf("A"), leaf("B")), both, reason)
    assert fields["ccfIncomplete"] is True and fields["ccfIncompleteReason"] == reason
    broken = {"ccfGroups": [group(beta="abc")]}
    fields = ccf.summary_fields(tree(leaf("A"), leaf("B")), broken, reason)
    assert fields["ccfIncomplete"] is False and "ccfIncompleteReason" not in fields


def test_engine_summary_adds_the_keys_only_for_a_document_with_groups(monkeypatch):
    from fta_web import cutsets, engine

    plain = engine.summary(tree(leaf("A"), leaf("B")), {})
    assert "ccf" not in plain and "ccfIncomplete" not in plain
    with_group = engine.summary(tree(leaf("A"), leaf("B")), {"ccfGroups": [group()]})
    assert with_group["ccfIncomplete"] is False and with_group["ccf"]["applied"][0]["id"] == "g1"

    def boom(*_args, **_kwargs):
        raise RuntimeError("test seam")

    monkeypatch.setattr(cutsets, "compute", boom)
    failed = engine.summary(tree(leaf("A"), leaf("B")), {"ccfGroups": [group()]})
    assert failed["ccfIncomplete"] is True and failed["ccfIncompleteReason"] == "error"


# ---- texts -------------------------------------------------------------------------------


def test_text_replaces_named_placeholders_and_keeps_literal_braces():
    assert ccf_text.text("en", "notApplied", reason="ETA mode") == "Not applied: ETA mode"
    assert ccf_text.text("ja", "notApplied", reason="ETA モード") == "未適用: ETA モード"
    assert "{C_AB, C_AC}" in ccf_text.text("en", "report.overlap")
    assert ccf_text.text("fr", "applied") == "Applied"  # anything but ja reads English
    with pytest.raises(KeyError):
        ccf_text.text("en", "no such key")


def test_the_two_groups_text_says_neither_group_is_applied():
    texts = ccf_text.lint_text("CCF_MEMBER_IN_TWO_GROUPS", None,
                               {"group": "G1", "member": "Pump A", "other": "G2"})
    assert "neither group is applied" in texts["en"]["message"]
    assert "G1" in texts["ja"]["message"] and "G2" in texts["ja"]["message"]


# ---- no mutation payload leaks a private key after a duplicate-id open ------------------


def _renamed_document():
    top = tree(
        dict(leaf("G1"), name="Pumps fail", children=[leaf("A"), leaf("B")]),
        dict(leaf("G2"), name="Other", children=[dict(leaf("A"), name="Pump A twin"), leaf("D")]),
    )
    return {"title": "t", "date": "2026-01-01", "mode": "FTA", "fileFormatVersion": 2,
            "tree": top, "analysis": {"ccfGroups": [group()]}}


@pytest.fixture
def opened(tmp_path):
    flask = pytest.importorskip("flask")
    from fta_web.routes.analysis import analysis_bp
    from fta_web.routes.ccf import ccf_bp
    from fta_web.routes.files import files_bp
    from fta_web.routes.fmea import fmea_bp
    from fta_web.routes.tree import tree_bp
    from fta_web.state import get_state, reset_state

    reset_state()
    app = flask.Flask(__name__)
    for blueprint in (tree_bp, files_bp, analysis_bp, fmea_bp, ccf_bp):
        app.register_blueprint(blueprint)
    app.config.update(TESTING=True)
    state = get_state()
    state.fs_root = tmp_path
    path = tmp_path / "dup.json"
    path.write_text(json.dumps(_renamed_document()), encoding="utf-8")
    csv_path = tmp_path / "fmea.csv"
    csv_path.write_text("FMEA ID,Item,Failure Mode,Failure rate\nF-1,Relief,Leaks,1e-6\n",
                        encoding="utf-8")
    with app.test_client() as client:
        response = client.post("/api/file/open", json={"path": str(path), "force": True})
        assert response.status_code == 200, response.get_data()
        yield client, state, _json(response), csv_path
    reset_state()


def _fmea_body(csv_path):
    return {"path": str(csv_path), "parentId": "root", "update": True, "lambdaUnit": "h",
            "mapping": {"id": "FMEA ID", "item": "Item", "mode": "Failure Mode",
                        "lambda": "Failure rate"}}


MUTATIONS = [
    ("open", None),
    ("state", ("get", "/api/state", None)),
    ("tree", ("patch", "/api/nodes/B", {"name": "Pump B2"})),
    ("settings", ("post", "/api/analysis/settings", {"missionTime": 50})),
    ("fmea", ("post", "/api/fmea/import", "fmea")),
    ("ccf", ("patch", "/api/ccf/groups/g1", {"name": "Renamed group"})),
]


@pytest.mark.parametrize("label, call", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_payloads_after_a_duplicate_id_open_carry_no_private_ccf_key(opened, label, call):
    client, state, open_body, csv_path = opened
    assert state.core.analysis["_ccfRenamed"] == {"g1": ["A"]}  # the flag exists in the engine
    if call is None:
        analysis = open_body["analysis"]
    else:
        method, url, body = call
        if body == "fmea":
            body = _fmea_body(csv_path)
        kwargs = {"json": body} if body is not None else {}
        response = client.open(url, method=method.upper(), **kwargs)
        assert response.status_code == 200, response.get_data()
        analysis = _json(response)["analysis"]
    assert "ccfGroups" in analysis
    assert [key for key in analysis if key.startswith("_ccf")] == []
