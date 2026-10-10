"""
Regression tests for the 2026-10 review of the analysis engine (finding ids
E-n). Each test failed before its fix.
"""
import copy

import pytest

from fta_web import engine
from fta_web.engine import WebCore


def leaf(node_id, p, **extra):
    node = {"id": node_id, "name": node_id, "type": "Event", "probability": p,
            "logicGate": "OR", "notes": "", "links": [], "children": []}
    node.update(extra)
    return node


def gate(node_id, gate_type, children, **extra):
    node = {"id": node_id, "name": node_id, "type": "Event", "probability": 1.0,
            "logicGate": "AND" if gate_type in ("AND", "INHIBIT", "PAND") else "OR",
            "notes": "", "links": [], "children": children}
    if gate_type not in ("AND", "OR"):
        node["gateType"] = gate_type
    node.update(extra)
    return node


def calc(tree, analysis=None):
    core = WebCore()
    core.set_data(copy.deepcopy(tree))
    if analysis:
        core.set_analysis(analysis)
    core.recalculate_probabilities()
    return core


# ---- E-2: an invalid own T is a missing parameter, not "use the mission time" ------------


@pytest.mark.parametrize("bad_t", ["1000", -1000.0, float("nan"), float("inf"), True])
def test_rate_with_an_invalid_own_t_keeps_its_probability_and_warns(bad_t):
    """USER_GUIDE: a model whose parameters are missing *or invalid* keeps its
    previous probability and reports QUANT_PARAM_MISSING. An invalid own T
    used to be treated as absent and silently replaced by the mission time:
    T = "1000" (a string in a hand-edited file) gave q = 1 - e^(-1e-4 * 8760)
    = 0.58 instead of the intended 0.095, with no warning anywhere."""
    quant = {"model": "rate", "lambda": 1e-4, "T": bad_t}
    core = calc(gate("root", "OR", [leaf("a", 0.05, quant=quant)]))
    assert core.find_node_by_id("a")["probability"] == 0.05
    assert [w["code"] for w in core.quant_warnings] == ["QUANT_PARAM_MISSING"]
    assert core.quant_warnings[0]["params"]["missing"] == ["T"]
    derived = engine.derive_quant({"id": "a", "probability": 0.05, "quant": quant})
    assert derived["q"] is None and derived["params"]["TFromMission"] is False


@pytest.mark.parametrize("quant", [
    {"model": "rate", "lambda": 1e-4},
    {"model": "rate", "lambda": 1e-4, "T": None},
])
def test_rate_without_an_own_t_still_uses_the_mission_time(quant):
    derived = engine.derive_quant({"id": "a", "probability": 0.05, "quant": quant},
                                  {"missionTime": 1000.0})
    assert derived["params"]["TFromMission"] is True and derived["params"]["T"] == 1000.0
    assert derived["q"] == pytest.approx(-__import__("math").expm1(-0.1))
    assert derived["warnings"] == []


# ---- E-4: a link loop that passes through a transfer is a loop too ------------------------


def _cyclic(tree):
    from fta_web import lint

    return sorted((i["code"], i["nodeId"]) for i in lint.run(tree, None)
                  if i["code"] == "CYCLIC_LINK")


def test_cyclic_link_through_a_transfer_is_reported():
    """X -(OR-link)-> T -(transfer)-> Y -(OR-link)-> X is the same loop as
    X -> Y -> X: the engine resolves both with the gate-only fallback and
    counts X twice (X = 0.352 = OR(0.1, OR(0.2, 0.1))). Lint built its loop
    graph from child edges and links only, so the version with a transfer
    was not reported at all."""
    through_transfer = gate("root", "OR", [
        leaf("X", 0.1, links=[{"target_id": "T", "relation": "OR"}]),
        gate("T", "TRANSFER", [], transferTo="Y"),
        leaf("Y", 0.2, links=[{"target_id": "X", "relation": "OR"}]),
    ])
    links_only = gate("root", "OR", [
        leaf("X", 0.1, links=[{"target_id": "Y", "relation": "OR"}]),
        leaf("Y", 0.2, links=[{"target_id": "X", "relation": "OR"}]),
    ])
    assert calc(through_transfer).find_node_by_id("X")["calculatedProbability"] == \
        calc(links_only).find_node_by_id("X")["calculatedProbability"] == pytest.approx(0.352)
    assert _cyclic(links_only) == [("CYCLIC_LINK", "X"), ("CYCLIC_LINK", "Y")]
    assert _cyclic(through_transfer) == [("CYCLIC_LINK", "X"), ("CYCLIC_LINK", "Y")]


def test_transfer_edges_do_not_flag_links_outside_a_loop():
    from fta_web import lint

    # T transfers to G and A AND-links to G: no loop, nothing to report.
    tree = gate("root", "OR", [
        gate("G", "AND", [leaf("B", 0.1), leaf("C", 0.2)]),
        gate("T", "TRANSFER", [], transferTo="G"),
        leaf("A", 0.3, links=[{"target_id": "G", "relation": "AND"}]),
    ])
    assert _cyclic(tree) == []
    # A transfer loop without any link stays TRANSFER_CYCLE's business.
    loop = gate("root", "OR", [gate("G", "OR", [gate("T", "TRANSFER", [], transferTo="G"),
                                               leaf("B", 0.1)])])
    codes = [i["code"] for i in lint.run(loop, None)]
    assert "TRANSFER_CYCLE" in codes and "CYCLIC_LINK" not in codes


# ---- E-5: an integer too large for a float is invalid, not a crash ------------------------

#: What ``json.loads`` makes of a 401-digit integer literal: an int that
#: ``float()`` refuses with OverflowError (not ValueError).
HUGE = 10 ** 400


def test_huge_integer_node_parameter_is_a_400_not_a_500():
    from fta_web import node_schema
    from fta_web.errors import ApiError

    for partial, field in (({"lambda": HUGE}, "quant.lambda"), ({"T": HUGE}, "quant.T"),
                           ({"unc": {"ef": HUGE}}, "quant.unc.ef")):
        with pytest.raises(ApiError) as info:
            node_schema.validate_quant(partial)
        assert info.value.detail["field"] == field


def test_huge_integer_analysis_setting_is_rejected_or_reset():
    for patch in ({"missionTime": HUGE}, {"cutsets": {"cutoff": HUGE}},
                  {"fmeaOccurrenceTable": {"3": HUGE}}):
        with pytest.raises(engine.AnalysisError):
            engine.merge_analysis(engine.default_analysis(), patch)
    analysis, problems = engine.coerce_analysis({"missionTime": HUGE, "mc": {"n": 50}})
    assert problems == ["missionTime"]
    assert analysis["missionTime"] == 8760.0 and analysis["mc"]["n"] == 50


def test_huge_integer_model_parameter_keeps_the_old_probability():
    core = calc(gate("root", "OR", [leaf("a", 0.125, quant={"model": "rate", "lambda": HUGE})]))
    assert core.find_node_by_id("a")["probability"] == 0.125
    assert [w["code"] for w in core.quant_warnings] == ["QUANT_PARAM_MISSING"]


def test_file_with_a_huge_integer_setting_loads_with_a_repair_notice(tmp_path):
    """The analysis block of a file is coerced on load: an invalid setting is
    reset with a LOAD_REPAIR notice (API_REFERENCE). A 401-digit integer
    raised OverflowError out of load_from_json instead (a 500 on open)."""
    path = tmp_path / "huge.json"
    path.write_text('{"title": "t", "tree": {"id": "root", "name": "top", "children": []},'
                    ' "analysis": {"missionTime": 1%s}}' % ("0" * 400), encoding="utf-8")
    core = WebCore()
    assert core.load_from_json(str(path)) == (True, None)
    assert core.analysis["missionTime"] == 8760.0
    assert [w["fields"] for w in core.last_load_warnings
            if w["kind"] == "analysis_invalid"] == [["missionTime"]]


# ---- E-1: an advanced name in logicGate is promoted to gateType; others are OR as in 1.6 ---


def _write_document(tmp_path, tree, name="doc.json"):
    import json

    path = tmp_path / name
    path.write_text(json.dumps({"title": "t", "date": "2026-10-10", "mode": "FTA", "tree": tree}),
                    encoding="utf-8")
    return str(path)


def _cut_ids(result):
    return sorted(sorted(e["id"] for e in c["events"]) for c in result["cutSets"])


def _three_half(raw_logic_gate):
    """A legacy-format tree: no 1.7 keys, logicGate as written, three 0.5 leaves."""
    return {"id": "root", "name": "top", "type": "Event", "probability": 1.0,
            "logicGate": raw_logic_gate,
            "children": [{"id": c, "name": c, "type": "Event", "probability": 0.5, "children": []}
                         for c in "ABC"]}


@pytest.mark.parametrize("raw, gate_type", [
    ("PAND", "PAND"), ("INHIBIT", "INHIBIT"), ("XOR", "XOR"), ("KOFN", "KOFN"),
    ("TRANSFER", "TRANSFER"), ("pand", "PAND"), (" Xor ", "XOR"),
])
def test_an_advanced_name_in_logic_gate_is_promoted_on_load_with_a_notice(tmp_path, raw, gate_type):
    """No 1.6 program writes an advanced gate name into logicGate, so one there
    (a hand edit) means that gate. It becomes the gateType, logicGate becomes
    its AND/OR projection, and a LOAD_REPAIR notice says so."""
    from fta_web import node_schema
    from fta_web.state import load_warning_issues

    core = WebCore()
    assert core.load_from_json(_write_document(tmp_path, _three_half(raw))) == (True, None)
    data = core.get_data()
    assert data["gateType"] == gate_type
    assert data["logicGate"] == node_schema.project_logic_gate(gate_type)
    promoted = [w for w in core.last_load_warnings if w["kind"] == "gate_type_promoted"]
    assert len(promoted) == 1 and promoted[0]["cause"] == "desktop"
    assert promoted[0]["gateType"] == gate_type and promoted[0]["new_id"] == "root"
    assert promoted[0]["logicGate"] == data["logicGate"]
    issue = load_warning_issues(promoted)[0]
    assert issue["code"] == "LOAD_REPAIR" and issue["nodeId"] == "root"
    assert gate_type in issue["message"]


def test_a_promoted_pand_is_the_same_gate_everywhere(tmp_path):
    """Legacy logicGate "PAND": tree walk, cut sets, headline, Validation and the
    display key (gateType) all say Priority-AND."""
    from fta_web import cutsets, lint
    from fta_web.state import load_warning_issues

    core = WebCore()
    assert core.load_from_json(_write_document(tmp_path, _three_half("PAND")))[0]
    data, analysis = core.get_data(), core.analysis
    assert data["gateType"] == "PAND" and data["logicGate"] == "AND"
    assert data["calculatedProbability"] == pytest.approx(0.125 / 6)
    result = cutsets.compute(data, analysis)
    assert _cut_ids(result) == [["A", "B", "C"]]
    assert [a["code"] for a in result["approximations"]] == ["PAND_APPROX"]
    summary = engine.summary(data, analysis)
    assert summary["headlineMethod"] == "treeWalk"
    assert summary["headline"] == data["calculatedProbability"]
    issues = lint.run(data, analysis, load_warning_issues(core.last_load_warnings))
    assert [(i["code"], i["params"].get("kind")) for i in issues] == [
        ("LOAD_REPAIR", "gate_type_promoted"), ("PAND_APPROX", None)]


def test_a_promoted_gate_without_its_parameter_is_reported(tmp_path):
    """KOFN without k and TRANSFER without transferTo: the existing errors say so."""
    from fta_web import lint

    for raw, code in (("KOFN", "KOFN_ARITY"), ("TRANSFER", "TRANSFER_MISSING")):
        core = WebCore()
        assert core.load_from_json(_write_document(tmp_path, _three_half(raw)))[0]
        assert code in [i["code"] for i in lint.run(core.get_data(), core.analysis)
                        if i["severity"] == "error"]


def test_the_ai_cause_is_named_in_a_promotion_notice():
    """reconcile_gate_types also runs on both AI paths (cause "ai")."""
    from fta_web import node_schema

    tree = _three_half("xor")
    warnings = node_schema.reconcile_gate_types(tree, cause="ai")
    assert tree["gateType"] == "XOR" and tree["logicGate"] == "OR"
    assert [(w["kind"], w["cause"]) for w in warnings] == [("gate_type_promoted", "ai")]
    assert "AI assistant" in warnings[0]["message"]


@pytest.mark.parametrize("raw", ["NAND", "FOO", "NOT", "nor"])
def test_an_unknown_logic_gate_still_computes_as_or_like_1_6(tmp_path, raw):
    """USER_GUIDE: a file without the 1.7 keys behaves exactly as in 1.6, and
    1.6 reads every logicGate but AND as OR. The engine and logic.py used to
    read the raw string, so a name they knew was computed as that gate."""
    from FTA_Editor_core import FTACore

    from fta_web import cutsets, lint

    path = _write_document(tmp_path, _three_half(raw))
    legacy, web = FTACore(), WebCore()
    assert legacy.load_from_json(path)[0] and web.load_from_json(path)[0]
    data, analysis = web.get_data(), web.analysis
    assert "gateType" not in data and web.last_load_warnings == []
    assert data["calculatedProbability"] == legacy.get_data()["calculatedProbability"] == 0.875
    assert web.quant_warnings == []
    result = cutsets.compute(data, analysis)
    assert _cut_ids(result) == [["A"], ["B"], ["C"]]
    assert result["nonCoherent"] is False and result["approximations"] == []
    summary = engine.summary(data, analysis)
    assert summary["headlineMethod"] == "treeWalk" and summary["headline"] == 0.875
    assert lint.run(data, analysis) == []


def test_the_promotion_notice_is_translated_for_the_validation_tab():
    """messageFor() tries val.code.LOAD_REPAIR.<kind>.<cause>, then .<kind>;
    every {param} must be one the warning carries."""
    import re
    from pathlib import Path

    from fta_web import node_schema

    warning = node_schema.reconcile_gate_types(_three_half("PAND"))[0]
    src = (Path(__file__).resolve().parents[1] / "static" / "js" / "i18n" / "val.js"
           ).read_text(encoding="utf-8")
    en_block, ja_block = src.split("\n  ja:", 1)
    for block in (en_block, ja_block):
        for key in ("val.code.LOAD_REPAIR.gate_type_promoted",
                    "val.code.LOAD_REPAIR.gate_type_promoted.ai"):
            text = re.search(r"'%s':\s*'([^']*)'" % re.escape(key), block).group(1)
            assert set(re.findall(r"\{(\w+)\}", text)) <= set(warning), (key, text)


def test_the_engine_itself_never_reads_a_gate_type_out_of_logic_gate():
    """Promotion is reconcile_gate_types' job (load, AI). A tree that skipped it
    (set_data) computes a raw "PAND" logicGate as OR, exactly as 1.6 does."""
    core = calc(_three_half("PAND"))
    assert core.get_data()["calculatedProbability"] == 0.875 and core.quant_warnings == []


@pytest.mark.parametrize("gate_type, extra, probs, expected", [
    ("XOR", {}, [0.1, 0.2], 0.1 + 0.2 - 2 * 0.1 * 0.2),
    ("PAND", {}, [0.1, 0.2], 0.1 * 0.2 / 2),
    ("KOFN", {"k": 2}, [0.1, 0.2, 0.3], engine.kofn_probability([0.1, 0.2, 0.3], 2)),
    ("TRANSFER", {"transferTo": "B"}, [0.1, 0.2], 0.2),
])
def test_gate_type_beside_a_same_named_logic_gate_survives_load_and_ai_reconcile(
        tmp_path, gate_type, extra, probs, expected):
    """The desktop app only ever writes AND or OR into logicGate, so a
    gateType beside a logicGate that names the same gate (a hand-written
    file) is not a desktop edit: it was dropped as "stale" together with its
    k, and the node computed something else. It is kept now, and logicGate
    becomes its AND/OR projection, without a repair notice."""
    from fta_web import node_schema

    children = [{"id": "AB"[i] if i < 2 else "C", "name": "x", "type": "Event",
                 "probability": p, "children": []} for i, p in enumerate(probs)]
    if gate_type == "TRANSFER":
        tree = {"id": "root", "name": "top", "type": "Event", "probability": 1.0,
                "logicGate": "OR", "children": [
                    {"id": "t", "name": "t", "type": "Event", "probability": 1.0,
                     "logicGate": gate_type, "gateType": gate_type, "children": [], **extra},
                    children[1]]}
        node_of = lambda root: root["children"][0]  # noqa: E731
    else:
        tree = {"id": "root", "name": "top", "type": "Event", "probability": 1.0,
                "logicGate": gate_type, "gateType": gate_type, "children": children, **extra}
        node_of = lambda root: root  # noqa: E731
    projected = node_schema.project_logic_gate(gate_type)

    core = WebCore()
    assert core.load_from_json(_write_document(tmp_path, tree)) == (True, None)
    node = node_of(core.get_data())
    assert node["gateType"] == gate_type and node["logicGate"] == projected
    for key, value in extra.items():
        assert node[key] == value
    assert not [w for w in core.last_load_warnings if w["kind"] == "gate_type_reset"]
    assert node["calculatedProbability"] == pytest.approx(expected)

    ai_tree = copy.deepcopy(tree)
    assert node_schema.reconcile_gate_types(ai_tree, cause="ai") == []
    node = node_of(ai_tree)
    assert node["gateType"] == gate_type and node["logicGate"] == projected
    for key, value in extra.items():
        assert node[key] == value


def test_a_desktop_gate_edit_still_resets_the_stale_gate_type(tmp_path):
    """Unchanged: gateType KOFN beside the desktop app's logicGate AND is stale."""
    tree = {"id": "root", "name": "top", "type": "Event", "probability": 1.0,
            "logicGate": "AND", "gateType": "KOFN", "k": 1, "children": [
                {"id": "A", "name": "A", "type": "Event", "probability": 0.5, "children": []},
                {"id": "B", "name": "B", "type": "Event", "probability": 0.5, "children": []}]}
    core = WebCore()
    assert core.load_from_json(_write_document(tmp_path, tree))[0]
    assert "gateType" not in core.get_data() and "k" not in core.get_data()
    assert core.get_data()["calculatedProbability"] == 0.25
    assert [w["kind"] for w in core.last_load_warnings] == ["gate_type_reset"]


# ---- E-3: Monte Carlo says when an uncertain event is in no sampled cut set ---------------

_UNC_B = {"model": "fixed", "unc": {"dist": "lognormal", "median": 0.05, "ef": 3.0}}


def _mc_tree(b_probability):
    """B is uncertain; the OR-link on g3 repeats E, so the cut-set method runs."""
    return gate("root", "OR", [
        gate("g1", "AND", [leaf("A", 0.1), leaf("B", b_probability, quant=copy.deepcopy(_UNC_B))]),
        gate("g2", "AND", [leaf("C", 0.1), leaf("D", 0.2)]),
        gate("g3", "AND", [leaf("E", 0.01), leaf("F", 0.01)],
             links=[{"target_id": "E", "relation": "OR"}]),
    ])


def test_mc_warns_when_an_uncertain_event_is_in_no_sampled_cut_set():
    """B's point value is 0 but its lognormal median is 0.05. The cut-set
    method picks sets by their point probability, and the expansion drops a
    P = 0 set without a truncation flag, so {A, B} was never sampled: std 0,
    p95 = point estimate, B still listed as uncertain, and no warning at all."""
    from fta_web import uncertainty

    result = uncertainty.run(_mc_tree(0.0), None, n=200, seed=7)
    assert result["method"] == "cutsets" and result["uncertainEvents"] == ["B"]
    found = [w for w in result["warnings"] if w["code"] == "MC_EVENT_NOT_SAMPLED"]
    assert found == [{"code": "MC_EVENT_NOT_SAMPLED", "nodeId": None,
                      "params": {"count": 1, "eventIds": ["B"], "names": "B"}}]
    # A warning, not a numeric change: the samples are what they were.
    assert result["std"] == 0.0 and result["mean"] == result["pointEstimate"]


def test_mc_does_not_warn_when_every_uncertain_event_is_sampled():
    from fta_web import uncertainty

    sampled = uncertainty.run(_mc_tree(0.05), None, n=200, seed=7)
    assert sampled["method"] == "cutsets" and sampled["std"] > 0
    assert "MC_EVENT_NOT_SAMPLED" not in [w["code"] for w in sampled["warnings"]]
    tree_method = uncertainty.run(gate("root", "OR", [
        leaf("A", 0.0, quant=copy.deepcopy(_UNC_B)), leaf("B", 0.1)]), None, n=50, seed=7)
    assert tree_method["method"] == "tree"
    assert "MC_EVENT_NOT_SAMPLED" not in [w["code"] for w in tree_method["warnings"]]


def test_mc_event_not_sampled_is_translated_for_the_uncertainty_tab():
    """renderWarnings() looks up anl.warn.<code>; without an entry the tab
    shows the bare code."""
    import re
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "static" / "js" / "i18n" / "cutsets.js"
           ).read_text(encoding="utf-8")
    en_block, ja_block = src.split("\n  ja:", 1)
    for block in (en_block, ja_block):
        text = re.search(r"'anl\.warn\.MC_EVENT_NOT_SAMPLED':\s*'([^']*)'", block).group(1)
        assert set(re.findall(r"\{(\w+)\}", text)) == {"count", "names"}


# ---- E-6: a probability the engine uses must be a number in [0, 1] ------------------------


def _issues(tree, mode="FTA"):
    from fta_web import lint

    return lint.run(tree, None, mode=mode)


def _out_of_range(issues):
    return [(i["nodeId"], i["severity"]) for i in issues if i["code"] == "PROBABILITY_OUT_OF_RANGE"]


@pytest.mark.parametrize("bad", [1.5, -0.2, float("nan"), float("inf"), float("-inf"),
                                 "junk", True, None])
def test_probability_out_of_range_is_an_error_where_the_engine_uses_it(bad):
    """A file edited by hand loads leaf probabilities unchecked: 1.5 made a
    headline of 1.25 and -0.2 one of 0.4, and the Validation tab said
    nothing; NaN was reported as "Probability is 1.0 (the default)"."""
    tree = gate("root", "OR", [leaf("A", bad), leaf("B", 0.5)])
    issues = _issues(tree)
    assert _out_of_range(issues) == [("A", "error")]
    assert "DEFAULT_PROBABILITY" not in [i["code"] for i in issues]
    issue = [i for i in issues if i["code"] == "PROBABILITY_OUT_OF_RANGE"][0]
    assert issue["params"] == {"probability": bad} or bad != bad  # NaN != NaN
    assert "{" not in issue["message"]
    # An event tree uses every node's own probability.
    assert _out_of_range(_issues(tree, mode="ETA")) == [("A", "error")]


def test_probability_out_of_range_only_where_the_engine_uses_the_value():
    tree = gate("root", "OR", [
        gate("g", "AND", [leaf("A", 0.0), leaf("B", 1.0)], probability=7.0),  # gates ignore it
        leaf("H", 5.0, eventKind="house", houseState=True),                    # houseState is used
        leaf("R", -3.0, quant={"model": "rate", "lambda": 1e-4, "T": 100.0}),  # the model is used
        gate("T", "TRANSFER", [], transferTo="A", probability=9.0),             # the target is used
        leaf("S", "0.25"),                                                      # a number all the same
        leaf("F", 2.0, quant={"model": "fixed"}),                               # fixed: q as entered
    ])
    assert _out_of_range(_issues(tree)) == [("F", "error")]
    # ETA reads each node's own probability, whatever its gate, kind or model.
    assert sorted(_out_of_range(_issues(tree, mode="ETA"))) == [
        ("F", "error"), ("H", "error"), ("R", "error"), ("T", "error"), ("g", "error")]


def test_a_valid_default_probability_is_still_reported_as_default():
    tree = gate("root", "OR", [leaf("A", 1.0), leaf("B", 0.5)])
    codes = [i["code"] for i in _issues(tree)]
    assert "DEFAULT_PROBABILITY" in codes and "PROBABILITY_OUT_OF_RANGE" not in codes


# ---- E-9: no stale FTA gate warnings in the node view of an event tree ----------------------


@pytest.fixture
def tree_client():
    flask = pytest.importorskip("flask")
    from fta_web.routes.tree import tree_bp
    from fta_web.state import reset_state

    reset_state()
    app = flask.Flask(__name__)
    app.register_blueprint(tree_bp)
    app.config.update(TESTING=True)
    with app.test_client() as client:
        yield client
    reset_state()


def test_node_view_has_no_fta_gate_warnings_in_eta_mode(tree_client):
    """WebCore only refreshes quant_warnings in its FTA walk, so after a
    switch to ETA the node view kept serving the last FTA run's KOFN_ARITY
    (gates are not evaluated in an event tree)."""
    client = tree_client
    gid = client.post("/api/nodes", json={"parentId": "root", "name": "G"}).get_json()["nodeId"]
    assert client.post("/api/nodes", json={"parentId": gid, "name": "a",
                                           "probability": 0.5}).status_code == 200
    assert client.patch("/api/nodes/%s" % gid, json={"gateType": "KOFN", "k": 5}).status_code == 200

    def warning_codes():
        node = client.get("/api/nodes/%s" % gid).get_json()["node"]
        return [w["code"] for w in node["quantDerived"]["warnings"]]

    assert warning_codes() == ["KOFN_ARITY"]
    assert client.post("/api/metadata", json={"mode": "ETA"}).status_code == 200
    assert warning_codes() == []
    assert client.post("/api/metadata", json={"mode": "FTA"}).status_code == 200
    assert warning_codes() == ["KOFN_ARITY"]


# ---- b2b: MC_EVENT_NOT_SAMPLED is a documented difference from the 1.7.0 release ------------


def _mc_row(branch_warnings, release_warnings, extra_diffs=()):
    """A release->branch "mc" row as cli_rows() builds it: diffs are
    (key, this branch's value, the release's value)."""
    from fta_web.tests.b2b import b2b_lib as B

    row = B.Row("F14_mixed_plant.json", "release->branch", "mc", "mismatch", n=20)
    row.diffs = [("warnings", tuple(branch_warnings), tuple(release_warnings))] + list(extra_diffs)
    return row


def test_b2b_classifies_the_new_mc_warning_as_a_documented_fix():
    """A FULL run compares this branch with the 1.7.0 release (CLI and exe);
    F14 and O04 now also carry MC_EVENT_NOT_SAMPLED, so their mc rows must
    be a documented divergence, not a mismatch."""
    from fta_web.tests.b2b import b2b_lib as B

    row = _mc_row(("MC_CUTSETS_TRUNCATED", "MC_EVENT_NOT_SAMPLED"), ("MC_CUTSETS_TRUNCATED",))
    [out] = B.classify_release([row], set())
    assert out.status == "divergence" and B.FIX_MC_EVENT in out.note
    # Together with the 1.7.1 Monte Carlo last-digit differences on one row.
    row = _mc_row(("MC_EVENT_NOT_SAMPLED",), (), [("mean", 0.1, 0.1 + 1e-17)])
    [out] = B.classify_release([row], set())
    assert out.status == "divergence" and B.FIX_MC_EVENT in out.note


def test_b2b_keeps_any_other_mc_warning_difference_a_mismatch():
    from fta_web.tests.b2b import b2b_lib as B

    for branch, release in ((("MC_NO_UNCERTAINTY",), ()),              # another code
                            ((), ("MC_EVENT_NOT_SAMPLED",)),           # the other way round
                            (("MC_EVENT_NOT_SAMPLED", "X"), ("X", "Y"))):  # and one lost
        [out] = B.classify_release([_mc_row(branch, release)], set())
        assert out.status == "mismatch", (branch, release)
    row = _mc_row(("MC_EVENT_NOT_SAMPLED",), (), [("p95", 0.1, 0.2)])  # not FIX_MC's kind
    assert B.classify_release([row], set())[0].status == "mismatch"
