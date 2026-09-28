"""
Tests for fta_web/engine.py -- ``WebCore``, the 1.7 probability engine.

The load-bearing test is the first one: on a legacy tree (no 1.7 keys) the
subclass must produce *exactly* the numbers ``FTACore`` does -- same floats,
not approximately -- including through links, dangling links, self links,
cycles and duplicate ids. Everything else then checks the additions.
"""
import copy
import itertools
import json
import math
import random

import pytest

from FTA_Editor_core import FTACore  # noqa: E402  (conftest put core on sys.path)

from fta_web import engine
from fta_web.engine import WebCore, kofn_probability


# ---- helpers ------------------------------------------------------------------------


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


def all_calcs(tree):
    out = []
    stack = [tree]
    while stack:
        node = stack.pop()
        out.append((node.get("id"), node.get("calculatedProbability")))
        stack.extend(reversed(node.get("children") or []))
    return out


def random_tree(rng):
    """A random legacy tree: AND/OR gates in every spelling the core accepts,
    leaves with and without a probability, links of both relations to random
    nodes (ancestors, self, descendants), dangling links, duplicate ids."""
    counter = itertools.count()
    nodes = []

    def build(depth):
        nid = "n%d" % next(counter)
        node = {"id": nid, "name": nid, "links": []}
        nodes.append(node)
        n_children = rng.choice([0, 0, 1, 2, 3, 4]) if depth < 4 else 0
        if n_children:
            node["logicGate"] = rng.choice(["AND", "OR", "and", "Or", "", None, " AND "])
            if rng.random() < 0.3:
                node["probability"] = rng.random()
            node["children"] = [build(depth + 1) for _ in range(n_children)]
        else:
            r = rng.random()
            if r < 0.1:
                pass  # no probability at all
            elif r < 0.2:
                node["probability"] = rng.choice([0.0, 1.0])
            else:
                node["probability"] = rng.random() ** 3
            if rng.random() < 0.5:
                node["children"] = []
        return node

    root = build(0)
    ids = [n["id"] for n in nodes]
    for node in nodes:
        for _ in range(rng.choice([0, 0, 0, 1, 1, 2])):
            target = rng.choice(ids + ["missing", ""]) if rng.random() < 0.9 else node["id"]
            node["links"].append({
                "target_id": target,
                "relation": rng.choice(["AND", "OR", "and", None]),
            })
    if len(nodes) > 3 and rng.random() < 0.2:
        rng.choice(nodes[1:])["id"] = rng.choice(ids)  # a duplicate id
    return root


# ---- legacy equivalence ------------------------------------------------------------


@pytest.mark.parametrize("seed", range(200))
def test_matches_ftacore_exactly_on_random_legacy_trees(seed):
    rng = random.Random(seed)
    tree = random_tree(rng)

    legacy = FTACore()
    legacy.set_data(copy.deepcopy(tree))
    legacy.recalculate_probabilities()

    web = WebCore()
    web.set_data(copy.deepcopy(tree))
    web.recalculate_probabilities()

    assert all_calcs(web.get_data()) == all_calcs(legacy.get_data())
    assert web.get_data() == legacy.get_data()
    assert web.quant_warnings == []


def test_matches_ftacore_on_the_sample_file(sample_fta_path):
    legacy = FTACore()
    assert legacy.load_from_json(str(sample_fta_path))[0]
    web = WebCore()
    assert web.load_from_json(str(sample_fta_path))[0]
    assert web.get_data() == legacy.get_data()


def test_eta_mode_is_untouched():
    tree = gate("root", "AND", [leaf("a", 0.5), leaf("b", 0.2)])
    legacy, web = FTACore(), WebCore()
    for core in (legacy, web):
        core.set_data(copy.deepcopy(tree))
        core.mode = "ETA"
        core.recalculate_probabilities()
    assert web.get_data() == legacy.get_data()


# ---- quant models ---------------------------------------------------------------------


def test_rate_model_with_explicit_T():
    core = calc(gate("root", "OR", [leaf("a", 0.9, quant={"model": "rate", "lambda": 1e-6, "T": 1000})]))
    a = core.find_node_by_id("a")
    assert a["probability"] == pytest.approx(1 - math.exp(-1e-3), rel=1e-11)
    assert a["calculatedProbability"] == a["probability"]


def test_rate_model_T_defaults_to_mission_time():
    tree = gate("root", "OR", [leaf("a", 0.9, quant={"model": "rate", "lambda": 1e-5})])
    core = calc(tree, {"missionTime": 100})
    assert core.find_node_by_id("a")["probability"] == pytest.approx(1 - math.exp(-1e-3), rel=1e-11)
    core = calc(tree)  # default 8760 h
    assert core.find_node_by_id("a")["probability"] == pytest.approx(1 - math.exp(-0.0876), rel=1e-11)


def test_small_rates_are_not_flushed_to_zero():
    core = calc(gate("root", "OR", [leaf("a", 0.5, quant={"model": "rate", "lambda": 1e-12, "T": 1})]))
    assert core.find_node_by_id("a")["probability"] == pytest.approx(1e-12, rel=1e-9)


def test_standby_model_and_large_lambda_tau_warning():
    core = calc(gate("root", "OR", [leaf("a", 0.5, quant={"model": "standby", "lambda": 1e-4, "tau": 720})]))
    assert core.find_node_by_id("a")["probability"] == pytest.approx(0.036)
    assert core.quant_warnings == []

    core = calc(gate("root", "OR", [leaf("a", 0.5, quant={"model": "standby", "lambda": 1e-3, "tau": 720})]))
    assert core.find_node_by_id("a")["probability"] == 0.36
    assert [w["code"] for w in core.quant_warnings] == ["STANDBY_LARGE_LT"]

    core = calc(gate("root", "OR", [leaf("a", 0.5, quant={"model": "standby", "lambda": 1, "tau": 720})]))
    assert core.find_node_by_id("a")["probability"] == 1.0


def test_repairable_model_with_mu_and_with_mttr():
    core = calc(gate("root", "OR", [
        leaf("a", 0.5, quant={"model": "repairable", "lambda": 1e-4, "mu": 0.1}),
        leaf("b", 0.5, quant={"model": "repairable", "lambda": 1e-4, "mttr": 10}),
    ]))
    expected = 1e-4 / (1e-4 + 0.1)
    assert core.find_node_by_id("a")["probability"] == pytest.approx(expected)
    assert core.find_node_by_id("b")["probability"] == pytest.approx(expected)


def test_fixed_model_uses_the_entered_probability():
    core = calc(gate("root", "OR", [leaf("a", 0.25, quant={"model": "fixed"})]))
    assert core.find_node_by_id("a")["calculatedProbability"] == 0.25


@pytest.mark.parametrize("quant", [
    {"model": "rate"},
    {"model": "rate", "lambda": -1, "T": 10},
    {"model": "standby", "lambda": 1e-4},
    {"model": "repairable", "lambda": 1e-4},
    {"model": "rate", "lambda": "abc", "T": 5},
])
def test_bad_parameters_keep_the_old_probability_and_warn(quant):
    core = calc(gate("root", "OR", [leaf("a", 0.125, quant=quant)]))
    assert core.find_node_by_id("a")["probability"] == 0.125
    assert [w["code"] for w in core.quant_warnings] == ["QUANT_PARAM_MISSING"]
    assert core.quant_warnings[0]["nodeId"] == "a"


def test_derive_quant_shape():
    derived = engine.derive_quant({"id": "x", "probability": 0.1,
                                   "quant": {"model": "rate", "lambda": 2e-6}})
    assert set(derived) == {"model", "q", "formula", "formulaKey", "params", "warnings"}
    assert derived["formulaKey"] == "quant.formula.rate"
    assert derived["params"]["TFromMission"] is True
    assert derived["params"]["T"] == 8760.0


# ---- gate types ------------------------------------------------------------------------


def brute_force_kofn(probs, k):
    total = 0.0
    for states in itertools.product([0, 1], repeat=len(probs)):
        if sum(states) >= k:
            term = 1.0
            for s, p in zip(states, probs):
                term *= p if s else (1 - p)
            total += term
    return total


@pytest.mark.parametrize("seed", range(30))
def test_kofn_matches_brute_force(seed):
    rng = random.Random(seed)
    n = rng.randint(1, 8)
    probs = [rng.random() for _ in range(n)]
    for k in range(0, n + 2):
        assert kofn_probability(probs, k) == pytest.approx(brute_force_kofn(probs, k), abs=1e-12)


def test_kofn_gate_in_a_tree():
    probs = [0.1, 0.2, 0.3, 0.4]
    tree = gate("root", "KOFN", [leaf("e%d" % i, p) for i, p in enumerate(probs)], k=2)
    core = calc(tree)
    assert core.get_data()["calculatedProbability"] == pytest.approx(brute_force_kofn(probs, 2), abs=1e-11)
    assert core.quant_warnings == []


def test_kofn_with_k_above_n_is_zero_and_warns():
    core = calc(gate("root", "KOFN", [leaf("a", 0.5), leaf("b", 0.5)], k=3))
    assert core.get_data()["calculatedProbability"] == 0.0
    assert [w["code"] for w in core.quant_warnings] == ["KOFN_ARITY"]


def test_xor_two_inputs():
    core = calc(gate("root", "XOR", [leaf("a", 0.1), leaf("b", 0.2)]))
    assert core.get_data()["calculatedProbability"] == pytest.approx(0.1 + 0.2 - 2 * 0.02)
    assert core.quant_warnings == []


def test_xor_other_arity_warns():
    core = calc(gate("root", "XOR", [leaf("a", 0.1), leaf("b", 0.2), leaf("c", 0.3)]))
    assert [w["code"] for w in core.quant_warnings] == ["XOR_ARITY"]


def test_inhibit_is_and_with_the_condition():
    core = calc(gate("root", "INHIBIT", [leaf("a", 0.1), leaf("c", 0.5, eventKind="conditioning")]))
    assert core.get_data()["calculatedProbability"] == 0.05
    assert core.quant_warnings == []
    core = calc(gate("root", "INHIBIT", [leaf("a", 0.1), leaf("c", 0.5)]))
    assert [w["code"] for w in core.quant_warnings] == ["INHIBIT_ARITY"]


def test_inhibit_arity_matches_lint_exactly_two_inputs():
    """Three inputs with one conditioning event: lint flags it, so must the engine."""
    from fta_web import lint

    tree = gate("root", "INHIBIT", [leaf("a", 0.1), leaf("b", 0.2),
                                    leaf("c", 0.5, eventKind="conditioning")])
    core = calc(tree)
    assert [w["code"] for w in core.quant_warnings] == ["INHIBIT_ARITY"]
    assert core.quant_warnings[0]["params"] == {"conditions": 1, "n": 3}
    assert core.get_data()["calculatedProbability"] == pytest.approx(0.01)  # still AND
    assert any(i["code"] == "INHIBIT_ARITY" for i in lint.run(core.get_data(), None))


def test_house_and_transfer_write_the_derived_probability_for_the_desktop_app(tmp_path):
    """The 1.6 desktop app (plain FTACore) reads a leaf's ``probability``: a
    saved file must carry the derived house/transfer values, not stale ones."""
    sub = gate("sub", "AND", [leaf("a", 0.5), leaf("b", 0.4)])
    tree = gate("root", "OR", [
        sub,
        gate("t", "TRANSFER", [], transferTo="sub", probability=1.0),
        leaf("hon", 1.0, eventKind="house", houseState=True),
        leaf("hoff", 1.0, eventKind="house", houseState=False),
        gate("tmiss", "TRANSFER", [], transferTo="nowhere", probability=0.7),
    ])
    web = WebCore()
    web.set_data(copy.deepcopy(tree))
    web.recalculate_probabilities()
    assert web.find_node_by_id("t")["probability"] == 0.2
    assert web.find_node_by_id("hon")["probability"] == 1.0
    assert web.find_node_by_id("hoff")["probability"] == 0.0
    assert web.find_node_by_id("tmiss")["probability"] == 0.0
    path = tmp_path / "doc.json"
    assert web.save_to_json(str(path))[0]

    desktop = FTACore()
    assert desktop.load_from_json(str(path))[0]
    desktop.recalculate_probabilities()
    for node_id in ("t", "hon", "hoff", "tmiss", "root"):
        assert (desktop.find_node_by_id(node_id)["calculatedProbability"]
                == web.find_node_by_id(node_id)["calculatedProbability"]), node_id


def test_pand_is_product_over_n_factorial_and_flagged():
    core = calc(gate("root", "PAND", [leaf("a", 0.1), leaf("b", 0.2), leaf("c", 0.3)]))
    assert core.get_data()["calculatedProbability"] == pytest.approx(0.006 / 6)
    assert [w["code"] for w in core.quant_warnings] == ["PAND_APPROX"]


def test_transfer_takes_the_target_value():
    sub = gate("sub", "AND", [leaf("a", 0.5), leaf("b", 0.5)])
    tree = gate("root", "OR", [sub, gate("t", "TRANSFER", [], transferTo="sub")])
    core = calc(tree)
    assert core.find_node_by_id("t")["calculatedProbability"] == 0.25
    assert core.get_data()["calculatedProbability"] == pytest.approx(1 - 0.75 * 0.75)


def test_transfer_to_a_missing_node_is_zero_and_warns():
    core = calc(gate("root", "OR", [leaf("a", 0.5), gate("t", "TRANSFER", [], transferTo="nope")]))
    assert core.find_node_by_id("t")["calculatedProbability"] == 0.0
    assert [w["code"] for w in core.quant_warnings] == ["TRANSFER_MISSING"]


def test_transfer_cycle_is_zero_and_warns():
    tree = gate("root", "OR", [gate("t", "TRANSFER", [], transferTo="root"), leaf("a", 0.5)])
    core = calc(tree)
    assert core.find_node_by_id("t")["calculatedProbability"] == 0.0
    assert [w["code"] for w in core.quant_warnings] == ["TRANSFER_CYCLE"]
    assert core.get_data()["calculatedProbability"] == 0.5


def test_house_events():
    tree = gate("root", "AND", [
        leaf("a", 0.3),
        leaf("h", 0.3, eventKind="house", houseState=True),
    ])
    assert calc(tree).get_data()["calculatedProbability"] == 0.3
    tree["children"][1]["houseState"] = False
    assert calc(tree).get_data()["calculatedProbability"] == 0.0


def test_gate_type_wins_over_logic_gate():
    tree = gate("root", "OR", [leaf("a", 0.5), leaf("b", 0.5)], gateType="AND")
    assert calc(tree).get_data()["calculatedProbability"] == 0.25


# ---- analysis block, persistence -------------------------------------------------------


def test_analysis_defaults():
    core = WebCore()
    assert core.analysis["missionTime"] == 8760
    assert core.analysis["timeUnit"] == "h"
    assert core.analysis["cutsets"] == {"maxOrder": 6, "maxCount": 5000, "cutoff": 1e-15}
    assert core.analysis["mc"] == {"n": 10000, "seed": None}
    assert sorted(core.analysis["fmeaOccurrenceTable"], key=int) == [str(i) for i in range(1, 11)]


def test_set_analysis_deep_merges_and_validates():
    core = WebCore()
    core.set_analysis({"cutsets": {"maxOrder": 3}, "mc": {"seed": 42}})
    assert core.analysis["cutsets"] == {"maxOrder": 3, "maxCount": 5000, "cutoff": 1e-15}
    assert core.analysis["mc"]["seed"] == 42
    before = copy.deepcopy(core.analysis)
    with pytest.raises(engine.AnalysisError) as info:
        core.set_analysis({"missionTime": 10, "cutsets": {"maxOrder": 0}})
    assert info.value.field == "cutsets.maxOrder"
    assert core.analysis == before  # atomic
    core.set_analysis({"cutsets": {"maxOrder": None}})
    assert core.analysis["cutsets"]["maxOrder"] == 6


def test_analysis_round_trips_through_save_and_load(tmp_path):
    core = WebCore()
    core.set_data(gate("root", "OR", [leaf("root_0", 0.5, quant={"model": "rate", "lambda": 1e-4})]))
    core.set_analysis({"missionTime": 100, "mc": {"n": 500, "seed": 7},
                       "fmeaOccurrenceTable": {"5": 0.001}})
    path = tmp_path / "doc.json"
    assert core.save_to_json(str(path))[0]

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert list(on_disk) == ["title", "date", "mode", "tree", "analysis"]

    loaded = WebCore()
    assert loaded.load_from_json(str(path)) == (True, None)
    assert loaded.analysis == core.analysis
    assert loaded.find_node_by_id("root_0")["probability"] == pytest.approx(1 - math.exp(-0.01))


def test_a_file_without_analysis_gets_defaults(tmp_path, sample_fta_path):
    core = WebCore()
    core.set_analysis({"missionTime": 5})
    assert core.load_from_json(str(sample_fta_path))[0]
    assert core.analysis == engine.default_analysis()


def test_invalid_analysis_values_are_reset_with_a_load_warning(tmp_path):
    path = tmp_path / "doc.json"
    path.write_text(json.dumps({
        "title": "t", "date": "d", "mode": "FTA",
        "tree": leaf("root", 0.5),
        "analysis": {"missionTime": -5, "cutsets": {"maxOrder": 4}},
    }), encoding="utf-8")
    core = WebCore()
    assert core.load_from_json(str(path))[0]
    assert core.analysis["missionTime"] == 8760
    assert core.analysis["cutsets"]["maxOrder"] == 4
    assert [w["kind"] for w in core.last_load_warnings] == ["analysis_invalid"]


def test_unknown_and_new_node_keys_survive_save_and_load(tmp_path):
    tree = gate("root", "KOFN", [
        leaf("root_0", 0.5, customKey={"x": [1, 2]},
             trace={"requirementId": "REQ-1", "tags": ["a"]},
             fmea={"id": "F1", "severity": 7}),
        leaf("root_1", 0.5),
    ], k=1)
    core = WebCore()
    core.set_data(tree)
    path = tmp_path / "doc.json"
    assert core.save_to_json(str(path))[0]
    loaded = WebCore()
    assert loaded.load_from_json(str(path))[0]
    node = loaded.find_node_by_id("root_0")
    assert node["customKey"] == {"x": [1, 2]}
    assert node["trace"] == {"requirementId": "REQ-1", "tags": ["a"]}
    assert node["fmea"] == {"id": "F1", "severity": 7}
    assert loaded.get_data()["gateType"] == "KOFN" and loaded.get_data()["k"] == 1

    # The legacy core reads the same file and keeps the keys as well.
    legacy = FTACore()
    assert legacy.load_from_json(str(path))[0]
    assert legacy.find_node_by_id("root_0")["customKey"] == {"x": [1, 2]}


def test_summary_stub_shape():
    result = engine.summary(gate("root", "AND", [leaf("a", 0.5), leaf("b", 0.2)]),
                            engine.default_analysis())
    assert set(result) == {"treeWalk", "mcub", "rareEvent", "headline", "headlineMethod",
                           "repeatedEvents", "nonCoherent", "approximations", "truncated",
                           "elapsedMs",
                           # additive (debug pass 1): document truncation vs summary cap
                           "truncatedBy", "capped"}
    assert result["treeWalk"] == result["headline"] == 0.1
    assert result["headlineMethod"] == "treeWalk"
    assert result["mcub"] == pytest.approx(0.1) and result["truncated"] is False


# ---- analysis in undo/redo (through the app state) ---------------------------------------


def test_analysis_is_part_of_undo_and_redo():
    from fta_web.state import reset_state

    state = reset_state()
    state.push_undo()
    state.core.set_analysis({"missionTime": 42})
    assert state.undo()
    assert state.core.analysis["missionTime"] == 8760
    assert state.redo()
    assert state.core.analysis["missionTime"] == 42
    assert isinstance(state.core, WebCore)
