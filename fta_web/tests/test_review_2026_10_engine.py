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


# ---- E-1: logicGate is read as 1.6 reads it; a same-named gateType is not stale ------------


def _write_document(tmp_path, tree, name="doc.json"):
    import json

    path = tmp_path / name
    path.write_text(json.dumps({"title": "t", "date": "2026-10-10", "mode": "FTA", "tree": tree}),
                    encoding="utf-8")
    return str(path)


def _cut_ids(result):
    return sorted(sorted(e["id"] for e in c["events"]) for c in result["cutSets"])


@pytest.mark.parametrize("raw", ["PAND", "INHIBIT", "XOR", "KOFN", "pand", " Xor "])
def test_legacy_logic_gate_holding_an_advanced_name_computes_as_or(tmp_path, raw):
    """USER_GUIDE: a file without the 1.7 keys behaves exactly as in 1.6, and
    1.6 reads every logicGate but AND as OR. The web engine and logic.py
    read an advanced name there as that gate: OR-of-three-0.5 under a raw
    "PAND" gave 0.0208 (1.6 core and desktop: 0.875), "INHIBIT" 0.125, and
    "XOR" a tree walk of 0.5 with an MCUB headline of 0.875 -- while lint
    read the same node as OR."""
    from FTA_Editor_core import FTACore

    from fta_web import cutsets, lint

    tree = {"id": "root", "name": "top", "type": "Event", "probability": 1.0, "logicGate": raw,
            "children": [{"id": c, "name": c, "type": "Event", "probability": 0.5, "children": []}
                         for c in "ABC"]}
    path = _write_document(tmp_path, tree)
    legacy, web = FTACore(), WebCore()
    assert legacy.load_from_json(path)[0] and web.load_from_json(path)[0]
    data, analysis = web.get_data(), web.analysis
    assert data["calculatedProbability"] == legacy.get_data()["calculatedProbability"] == 0.875
    assert web.quant_warnings == []
    result = cutsets.compute(data, analysis)
    assert _cut_ids(result) == [["A"], ["B"], ["C"]]
    assert result["nonCoherent"] is False and result["approximations"] == []
    summary = engine.summary(data, analysis)
    assert summary["headlineMethod"] == "treeWalk" and summary["headline"] == 0.875
    assert lint.run(data, analysis) == []


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
