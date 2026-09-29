"""
Regression tests for the 1.7.0 backend debugging pass (pass 1: correctness
and robustness). Each test names the defect it pins; see the commit messages
for the root cause.
"""
import importlib
import json
import math
import os
import random

import pytest

from fta_web import cutsets, engine, fsbrowser, importance, logic, uncertainty
from fta_web.engine import WebCore


def leaf(node_id, p, **extra):
    node = {"id": node_id, "name": node_id, "type": "Event", "probability": p,
            "logicGate": "OR", "notes": "", "links": [], "children": []}
    node.update(extra)
    return node


def gate(node_id, gate_type, children, **extra):
    node = {"id": node_id, "name": node_id, "type": "Event", "probability": 1.0,
            "logicGate": engine.project_logic_gate(gate_type),
            "notes": "", "links": [], "children": children}
    if gate_type not in ("AND", "OR"):
        node["gateType"] = gate_type
    node.update(extra)
    return node


def walk_value(tree, analysis=None):
    core = logic.recalculated_core(tree, analysis)
    return core.get_data()["calculatedProbability"]


# ---- PAND with more than 170 inputs -------------------------------------------------
# 171! does not fit a float, so ``product / math.factorial(n)`` raised
# OverflowError in the engine, the formula graph and the Monte Carlo sampler
# -- and the summary's tree-walk fallback re-raised it as a 500.


def big_pand(n=200, p=0.9):
    return gate("root", "PAND", [leaf("e%d" % i, p) for i in range(n)])


def test_pand_divide_matches_factorial_below_the_limit_and_survives_above():
    for n in (0, 1, 2, 5, 170):
        assert engine.pand_divide(0.5, n) == 0.5 / math.factorial(n)
    from fractions import Fraction

    exact = float(Fraction(1, 2 * math.factorial(171)))
    assert engine.pand_divide(0.5, 171) == pytest.approx(exact, rel=1e-6)
    assert engine.pand_divide(1.0, 500) == 0.0
    assert engine.pand_divide(0.0, 500) == 0.0


def test_pand_with_200_inputs_does_not_overflow_anywhere():
    tree = big_pand()
    assert walk_value(tree) == 0.0
    s = logic.compile_tree(tree, None)
    assert s.evaluate() == 0.0
    result = cutsets.compute(tree, None, {"maxOrder": 20})
    assert result["truncated"] is True  # a 200-event cut set is above maxOrder
    out = uncertainty.run(tree, None, n=20, seed=1)
    assert out["mean"] == 0.0
    summary = engine.summary(tree, None)
    assert summary["headline"] == 0.0


# ---- MCUB of no cut sets --------------------------------------------------------------


def test_mcub_of_nothing_is_positive_zero():
    value = cutsets.mcub_of([])
    assert value == 0.0 and math.copysign(1.0, value) == 1.0
    result = cutsets.compute(leaf("root", 0.0), None)
    assert json.dumps(result["mcub"]) == "0.0"


# ---- summary: document truncation vs the summary's own cap ---------------------------


def many_cut_sets(width=13):
    """AND of three ORs of ``width`` events: width**3 minimal cut sets."""
    return gate("root", "AND", [
        gate("g%d" % g, "OR", [leaf("e%d_%d" % (g, i), 0.01 * (i + 1)) for i in range(width)])
        for g in range(3)
    ])


def test_summary_cap_is_not_reported_as_document_truncation():
    tree = many_cut_sets()  # 2197 cut sets; the document allows 5000
    analysis = engine.default_analysis()
    full = cutsets.compute(tree, analysis)
    assert full["truncated"] is False and full["total"] == 13 ** 3
    out = engine.summary(tree, analysis)
    assert out["capped"] is True
    assert out["truncated"] is False and out["truncatedBy"] == []


def test_summary_uses_a_lower_document_max_count_and_reports_it():
    tree = many_cut_sets(5)  # 125 cut sets
    analysis = engine.merge_analysis(engine.default_analysis(), {"cutsets": {"maxCount": 100}})
    full = cutsets.compute(tree, analysis)
    assert full["truncated"] is True and full["total"] == 100
    out = engine.summary(tree, analysis)
    assert out["truncated"] is True and out["truncatedBy"] == ["count"]
    assert out["capped"] is False
    assert out["mcub"] == pytest.approx(full["mcub"])


def test_summary_without_truncation_has_the_new_fields():
    out = engine.summary(gate("root", "OR", [leaf("a", 0.1), leaf("b", 0.2)]), None)
    assert out["truncated"] is False and out["capped"] is False and out["truncatedBy"] == []


def test_summary_fallback_on_error_is_truncated_but_not_capped():
    tree = gate("root", "KOFN", [leaf("e%d" % i, 0.01) for i in range(30)], k=10)
    out = engine.summary(tree, None)
    assert out["truncated"] is True and out["capped"] is False
    assert out["headlineMethod"] == "treeWalk" and out["mcub"] is None


def test_summary_timeout_is_capped(monkeypatch):
    def slow(*_args, **_kwargs):
        raise cutsets.CutsetError("time", "Cut set analysis exceeded its time budget.")

    monkeypatch.setattr(cutsets, "compute", slow)
    out = engine.summary(gate("root", "OR", [leaf("a", 0.1)]), None)
    assert out["truncated"] is True and out["capped"] is True
    assert out["headline"] == pytest.approx(0.1)


# ---- Monte Carlo with an extreme error factor ----------------------------------------
# EF is only bounded below (>= 1) by the schema, and a loaded file is not
# validated at all: exp(sigma * z) overflowed (OverflowError -> 500).


@pytest.mark.parametrize("unc", [
    {"dist": "lognormal", "ef": 1e308, "mean": 0.1},
    {"dist": "lognormal", "ef": 1e308, "median": 0.1},
    {"dist": "lognormal", "ef": 1e30, "median": 1e300},
])
def test_uncertainty_survives_an_extreme_error_factor(unc):
    for model in ({"model": "fixed"}, {"model": "rate", "lambda": 1e-4},
                  {"model": "repairable", "lambda": 1e-3, "mu": 0.1},
                  {"model": "standby", "lambda": 1e-4, "tau": 100}):
        quant = dict(model, unc=unc)
        tree = gate("root", "OR", [leaf("a", 0.1, quant=quant), leaf("b", 0.2)])
        out = uncertainty.run(tree, None, n=500, seed=3)
        assert out["completed"] == 500
        for key in ("mean", "median", "p05", "p95", "std"):
            assert out[key] is not None and 0.0 <= out[key] <= 1.0 or key == "std"
            assert not math.isnan(out[key])


def test_repairable_sample_at_the_overflow_edge_is_one_not_zero():
    """x / (x + mu) with an enormous sampled lambda is 1, never NaN -> 0."""
    unc = {"dist": "lognormal", "ef": 1e300, "median": 1e300}
    quant = {"model": "repairable", "lambda": 1e-3, "mu": 0.1, "unc": unc}
    out = uncertainty.run(leaf("root", 0.1, quant=quant), None, n=400, seed=5)
    # Half the samples of a median-1e300 lambda are at or above 1e300.
    assert out["p95"] == 1.0


# ---- responses are strict JSON ------------------------------------------------------------
# Python's json accepts NaN/Infinity (in a request body and in a file), and
# Flask echoed them back verbatim -- in an error's detail.value, or in the
# tree of a loaded file. The browser's JSON.parse rejects those tokens, so the
# frontend saw an unparseable response instead of the error / document.


def strict_loads(text):
    def refuse(token):
        raise ValueError("non-standard JSON token %s" % token)

    return json.loads(text, parse_constant=refuse)


@pytest.fixture
def app_client(tmp_path):
    from fta_web.app import create_app
    from fta_web.state import get_state, reset_state

    reset_state()
    app = create_app(fs_root=tmp_path)
    app.config.update(TESTING=True)
    get_state().fs_root = tmp_path
    # create_app() imports the blueprints by bare module name, so the app's
    # AppState singleton is the bare ``state`` module's: reset that one too.
    bare_state = importlib.import_module("state")
    bare_state.reset_state()
    bare_state.get_state().fs_root = tmp_path
    with app.test_client() as client:
        yield client


def test_an_error_echoing_nan_is_strict_json(app_client):
    node = strict_loads(app_client.post("/api/nodes", json={
        "parentId": "root", "name": "a"}).get_data(as_text=True))["nodeId"]
    for raw in ('{"quant": {"model": "rate", "lambda": NaN}}',
                '{"quant": {"model": "rate", "lambda": Infinity}}',
                '{"probability": -Infinity}'):
        response = app_client.patch("/api/nodes/%s" % node, data=raw,
                                    content_type="application/json")
        assert response.status_code == 400
        payload = strict_loads(response.get_data(as_text=True))
        assert payload["error"]["code"] == "INVALID_FIELD"
    response = app_client.post("/api/analysis/uncertainty", data='{"timeLimit": NaN}',
                               content_type="application/json")
    assert strict_loads(response.get_data(as_text=True))["error"]["detail"]["value"] is None


def test_a_file_with_non_finite_numbers_opens_as_strict_json(app_client, tmp_path):
    doc = {"title": "t", "date": "", "mode": "FTA", "tree": {
        "id": "root", "name": "Top", "type": "Event", "probability": 1.0, "logicGate": "OR",
        "notes": "", "links": [], "children": [
            {"id": "root_0", "name": "A", "type": "Event", "probability": float("nan"),
             "logicGate": "", "notes": "", "links": [], "children": [],
             "quant": {"model": "rate", "lambda": float("inf")}},
        ]}}
    target = tmp_path / "nan.json"
    target.write_text(json.dumps(doc), encoding="utf-8")  # writes NaN / Infinity
    for response in (app_client.post("/api/file/open", json={"path": str(target)}),
                     app_client.get("/api/state"),
                     app_client.get("/api/nodes/root_0"),
                     app_client.get("/api/analysis/summary")):
        assert response.status_code == 200
        strict_loads(response.get_data(as_text=True))


def test_fmea_import_with_a_non_string_lambda_unit_is_a_400(app_client):
    """``lambda_unit not in LAMBDA_UNITS`` (a dict) raised TypeError -> 500
    for a list or object value."""
    for unit in (["h"], {"h": 1}):
        response = app_client.post("/api/fmea/import", json={
            "path": "x.csv", "mapping": {}, "parentId": "root", "lambdaUnit": unit})
        assert response.status_code == 400
        assert strict_loads(response.get_data(as_text=True))["error"]["detail"]["field"] \
            == "lambdaUnit"


# ---- a deleted transfer target's id is handed out again --------------------------------
# DELETE strips links into the deleted subtree precisely because
# next_child_id may reuse a deleted id -- but a TRANSFER's transferTo was
# left pointing at the deleted id, so the next Add silently re-targeted the
# transfer at a new, unrelated node.


def api_json(response):
    assert response.status_code == 200, response.get_data(as_text=True)
    return strict_loads(response.get_data(as_text=True))


def test_deleting_a_transfer_target_clears_the_transfer(app_client):
    c = app_client
    target = api_json(c.post("/api/nodes", json={"parentId": "root", "name": "A",
                                                 "probability": 0.1}))["nodeId"]
    transfer = api_json(c.post("/api/nodes", json={"parentId": "root", "name": "T"}))["nodeId"]
    api_json(c.patch("/api/nodes/%s" % transfer,
                     json={"gateType": "TRANSFER", "transferTo": target}))

    deleted = api_json(c.delete("/api/nodes/%s" % target))
    assert {"nodeId": transfer, "targetId": target, "relation": "TRANSFER"} \
        in deleted["removedLinks"]
    assert any(w["code"] == "LINKS_REMOVED" and w["nodeId"] == transfer
               for w in deleted["sessionWarnings"])

    reused = api_json(c.post("/api/nodes", json={"parentId": "root", "name": "Unrelated",
                                                 "probability": 0.9}))
    node = api_json(c.get("/api/nodes/%s" % transfer))["node"]
    assert node["gateType"] == "TRANSFER" and node["transferTo"] is None
    # The transfer is dangling (0 and TRANSFER_MISSING), not the new node's 0.9.
    by_id = {n["id"]: n for n in reused["tree"]["children"]}
    assert by_id[transfer]["calculatedProbability"] == 0.0
    # Undo restores both the node and the transfer.
    api_json(c.post("/api/undo"))
    undone = api_json(c.post("/api/undo"))
    by_id = {n["id"]: n for n in undone["tree"]["children"]}
    assert by_id[transfer]["transferTo"] == target


def test_ai_delete_strips_links_and_transfers_to_the_removed_nodes(
        app_client, monkeypatch):
    """The AI 'delete' change goes through the vendored handler, which removes
    the node and nothing else: links and transfers kept pointing at the id."""
    ai_routes = importlib.import_module("routes.ai")  # the app's own module
    get_state = importlib.import_module("state").get_state

    c = app_client
    a = api_json(c.post("/api/nodes", json={"parentId": "root", "name": "A",
                                            "probability": 0.1}))["nodeId"]
    b = api_json(c.post("/api/nodes", json={"parentId": "root", "name": "B",
                                            "probability": 0.2,
                                            "links": [{"target_id": a, "relation": "AND"}]}))
    b = b["nodeId"]
    t = api_json(c.post("/api/nodes", json={"parentId": "root", "name": "T",
                                            "gateType": "TRANSFER", "transferTo": a}))["nodeId"]

    class Change:
        change_type = "delete"
        target_id = a

    class Handler:
        pending_changes = [Change()]

        def apply_change_to_fta(self, core, change):
            core.delete_node_from_data(change.target_id)
            return True, "deleted"

    monkeypatch.setattr(ai_routes, "_require_configured", lambda: None)
    monkeypatch.setattr(ai_routes.ai_bridge, "get_handler", lambda: Handler())
    monkeypatch.setattr(ai_routes.ai_bridge, "change_view",
                        lambda change, index: {"index": index})
    payload = api_json(c.post("/api/ai/changes/apply", json={"indices": [0]}))
    by_id = {n["id"]: n for n in payload["tree"]["children"]}
    assert by_id[b]["links"] == []
    assert "transferTo" not in by_id[t]
    codes = [(w["code"], w["nodeId"]) for w in get_state().session_warnings]
    assert ("LINKS_REMOVED", b) in codes and ("LINKS_REMOVED", t) in codes
    # The notices belong to the AI edit: undo removes them with it, redo
    # brings them back.
    undone = api_json(c.post("/api/undo"))
    assert not [w for w in undone["sessionWarnings"] if w["code"] == "LINKS_REMOVED"]
    redone = api_json(c.post("/api/redo"))
    assert {(w["code"], w["nodeId"]) for w in redone["sessionWarnings"]} >= {
        ("LINKS_REMOVED", b), ("LINKS_REMOVED", t)}


# ---- report options: whitelisted and validated -------------------------------------------
# routes/report.py handed the whole request body to normalize_options, so
# client 'limits' reached cutsets.compute unvalidated (maxOrder 999, a huge
# timeBudgetS) and 'generated' / anything else passed straight through.


@pytest.fixture
def report_client(tmp_path, monkeypatch):
    import flask

    from fta_web.routes import report as report_routes
    from fta_web.routes.report import report_bp
    from fta_web.state import get_state, reset_state

    reset_state()
    get_state().fs_root = tmp_path
    seen = {}

    def capture(snapshot, warnings, options):
        seen["options"] = options
        return {"captured": True}

    monkeypatch.setattr(report_routes.report_docx, "collect_report_data", capture)
    monkeypatch.setattr(report_routes.report_docx, "build_report", lambda data, options: b"PK")
    monkeypatch.setattr(report_routes, "docx_available", lambda: True)
    app = flask.Flask(__name__)
    app.register_blueprint(report_bp)
    app.config.update(TESTING=True)
    with app.test_client() as client:
        yield client, seen


@pytest.mark.parametrize("body, field", [
    ({"limits": {"maxOrder": 999}}, "limits.maxOrder"),
    ({"limits": {"maxCount": 0}}, "limits.maxCount"),
    ({"limits": {"cutoff": 2}}, "limits.cutoff"),
    ({"limits": {"timeBudgetS": 1e9}}, "limits"),
    ({"limits": "all"}, "limits"),
    ({"uncertaintyN": 10 ** 9}, "uncertaintyN"),
    ({"uncertaintyN": "5"}, "uncertaintyN"),
    ({"uncertaintyTimeLimit": 3600}, "uncertaintyTimeLimit"),
    ({"uncertaintyTimeLimit": 0}, "uncertaintyTimeLimit"),
])
def test_report_rejects_unvalidated_limits(report_client, body, field):
    client, seen = report_client
    response = client.post("/api/report/docx", json=dict(body, sections=["cutsets"]))
    assert response.status_code == 400, response.get_data(as_text=True)
    error = json.loads(response.get_data(as_text=True))["error"]
    assert error["code"] == "INVALID_FIELD" and error["detail"]["field"] == field
    assert "options" not in seen


def test_report_passes_only_whitelisted_options(report_client):
    client, seen = report_client
    response = client.post("/api/report/docx", json={
        "sections": ["cutsets", "uncertainty"], "limits": {"maxOrder": 3, "cutoff": 0},
        "uncertaintyN": 100, "uncertaintyTimeLimit": 5, "generated": "1970-01-01 forged",
        "uncertainty": {"mean": 0.5}, "runUncertainty": True, "bogus": 1})
    assert response.status_code == 200, response.get_data(as_text=True)
    options = seen["options"]
    assert options["limits"] == {"maxOrder": 3, "cutoff": 0.0}
    assert options["uncertaintyN"] == 100
    assert options.get("generated") is None
    assert options["uncertainty"] is None


# ---- load errors say what is wrong ----------------------------------------------------------
# The core reports every unparseable file -- empty, truncated, 'null' -- as
# "Failed to read file with common encodings", which sends the user hunting
# for an encoding problem that is not there (reported by pass 3).


@pytest.mark.parametrize("content, expected", [
    (b"", "empty"),
    (b"   \r\n\t ", "empty"),
    (b'{"title": "x", "tree": {"id": "root", ', "not valid JSON"),
    (b"{'single': 'quotes'}", "not valid JSON"),
    (b"null", "must be an object"),
])
def test_unparseable_files_get_a_clear_load_error(tmp_path, content, expected):
    target = tmp_path / "bad.json"
    target.write_bytes(content)
    ok, error = WebCore().load_from_json(str(target))
    assert ok is False
    assert expected in error and "encodings" not in error


def test_open_route_reports_invalid_json_clearly(app_client, tmp_path):
    target = tmp_path / "truncated.json"
    target.write_text('{"tree": {"id": "root"', encoding="utf-8")
    response = app_client.post("/api/file/open", json={"path": str(target)})
    assert response.status_code == 400
    message = strict_loads(response.get_data(as_text=True))["error"]["message"]
    assert "not valid JSON" in message and "line 1" in message


# ---- filesystem sandbox: Windows path forms ---------------------------------------------

windows_only = pytest.mark.skipif(os.name != "nt", reason="Windows path semantics")


@windows_only
@pytest.mark.parametrize("raw", ["notes.txt:evil.json", "notes.txt:x:$DATA.json",
                                 "sub\\notes.txt:evil.json"])
def test_alternate_data_streams_are_rejected(tmp_path, raw):
    """``notes.txt:evil.json`` passed the .json allow-list and wrote a hidden
    NTFS alternate data stream onto an arbitrary file inside the root."""
    (tmp_path / "notes.txt").write_text("secret")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "notes.txt").write_text("secret")
    root = fsbrowser.resolve_root(tmp_path)
    with pytest.raises(fsbrowser.PathRejected) as info:
        fsbrowser.resolve_in_root(raw, root)
    assert info.value.reason == "stream"
    with pytest.raises(fsbrowser.PathRejected):
        fsbrowser.resolve_for_write(raw, root, {".json"})


@windows_only
@pytest.mark.parametrize("raw", ["\\\\attacker.invalid\\share\\x.json",
                                 "//attacker.invalid/share/x.json",
                                 "\\\\?\\UNC\\attacker.invalid\\share\\x.json"])
def test_unc_paths_are_rejected_before_touching_the_network(tmp_path, monkeypatch, raw):
    """Resolving a UNC path opens it -- an SMB connection (and an NTLM
    handshake) to whatever host the client named -- before containment was
    checked. The drive must be compared lexically first."""
    root = fsbrowser.resolve_root(tmp_path)
    seen = []
    original = type(root).resolve

    def spy(self, *args, **kwargs):
        seen.append(str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(type(root), "resolve", spy)
    with pytest.raises(fsbrowser.PathRejected) as info:
        fsbrowser.resolve_in_root(raw, root)
    assert info.value.reason == "outside_root"
    assert not any("attacker" in s for s in seen)


@windows_only
def test_ordinary_windows_paths_still_work(tmp_path):
    root = fsbrowser.resolve_root(tmp_path)
    (tmp_path / "a.json").write_text("{}")
    assert fsbrowser.resolve_in_root(str(tmp_path / "a.json"), root) == root / "a.json"
    # Drive letter case and forward slashes are the same place.
    other_case = str(root / "a.json")
    other_case = other_case[0].swapcase() + other_case[1:]
    assert fsbrowser.resolve_in_root(other_case.replace("\\", "/"), root) == root / "a.json"
    assert fsbrowser.resolve_for_write("new.json", root, {".json"}) == root / "new.json"
