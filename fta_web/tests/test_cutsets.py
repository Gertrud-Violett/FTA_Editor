"""
Tests for fta_web/logic.py and fta_web/cutsets.py.

The load-bearing test is the brute-force one: on a few hundred seeded random
trees (links, transfers, KOFN, INHIBIT, house events, repeated events, link
and transfer cycles) the minimal cut sets must equal the minimal true
assignments of the structure function -- and the structure function is read
off the *engine itself* by setting every event to 0 or 1, so the cut sets are
checked against WebCore's semantics, not against a second copy of them.
"""
import copy
import itertools
import math
import random

import pytest

from fta_web import cutsets, engine, logic
from fta_web.engine import WebCore

NO_LIMITS = {"maxOrder": 20, "maxCount": 1_000_000, "cutoff": 0.0}


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


def ids(result):
    return sorted(sorted(e["id"] for e in cs["events"]) for cs in result["cutSets"])


# ---- textbook -------------------------------------------------------------------------


def test_textbook_shared_event():
    tree = gate("root", "OR", [
        gate("g1", "AND", [leaf("A", 0.1), leaf("B", 0.2)]),
        gate("g2", "AND", [leaf("A2", 0.1), leaf("C", 0.3)],
             links=[]),
    ])
    # A2 is A again, through a transfer.
    tree["children"][1]["children"][0] = gate("t", "TRANSFER", [], transferTo="A")
    result = cutsets.compute(tree, None, NO_LIMITS)
    assert ids(result) == [["A", "B"], ["A", "C"]]
    assert result["repeatedEvents"] == [{"id": "A", "name": "A"}]
    assert result["rareEvent"] == pytest.approx(0.02 + 0.03)
    assert result["mcub"] == pytest.approx(1 - 0.98 * 0.97)
    # The tree walk double-counts A: 1-(1-0.02)(1-0.03) -- same as MCUB here.
    assert result["treeWalk"] == pytest.approx(0.0494)
    first = result["cutSets"][0]
    assert first["rank"] == 1 and first["order"] == 2
    assert first["probability"] == pytest.approx(0.03)
    assert first["share"] == pytest.approx(0.6)
    assert set(first["events"][0]) == {"id", "name", "q"}


def test_absorption_and_empty_set():
    tree = gate("root", "OR", [leaf("A", 0.1), gate("g", "AND", [leaf("B", 0.2)])],
                links=[{"target_id": "A", "relation": "OR"}])
    tree["children"][1]["links"] = [{"target_id": "A", "relation": "AND"}]
    # g = B AND A (AND-link) -> absorbed by A.
    result = cutsets.compute(tree, None, NO_LIMITS)
    assert ids(result) == [["A"]]

    house = gate("root", "OR", [leaf("H", 0.0, eventKind="house", houseState=True),
                                leaf("A", 0.5)])
    result = cutsets.compute(house, None, NO_LIMITS)
    assert result["total"] == 1 and result["cutSets"][0]["events"] == []
    assert result["mcub"] == 1.0 and result["treeWalk"] == 1.0

    off = gate("root", "AND", [leaf("H", 1.0, eventKind="house", houseState=False),
                               leaf("A", 0.5)])
    result = cutsets.compute(off, None, NO_LIMITS)
    assert result["total"] == 0 and result["mcub"] == 0.0 and result["rareEvent"] == 0.0


def test_kofn_2_of_3():
    tree = gate("root", "KOFN", [leaf("A", 0.1), leaf("B", 0.2), leaf("C", 0.3)], k=2)
    result = cutsets.compute(tree, None, NO_LIMITS)
    assert ids(result) == [["A", "B"], ["A", "C"], ["B", "C"]]
    assert result["treeWalk"] == pytest.approx(engine.kofn_probability([0.1, 0.2, 0.3], 2))


def test_kofn_too_large_is_refused():
    tree = gate("root", "KOFN", [leaf("e%d" % i, 0.01) for i in range(30)], k=10)
    with pytest.raises(cutsets.CutsetError) as info:
        cutsets.compute(tree, None, NO_LIMITS)
    assert info.value.reason == "kofn"
    assert info.value.node_id == "root"
    assert info.value.params["combinations"] == math.comb(30, 10)


def test_time_budget():
    tree = gate("root", "AND", [
        gate("g%d" % g, "OR", [leaf("e%d_%d" % (g, i), 0.5) for i in range(10)])
        for g in range(8)
    ])
    with pytest.raises(cutsets.CutsetError) as info:
        cutsets.compute(tree, None, {"maxOrder": 8, "maxCount": 10 ** 6, "cutoff": 0,
                                     "timeBudgetS": 0.05})
    assert info.value.reason == "time"


def test_xor_is_read_as_or_and_flagged():
    tree = gate("root", "XOR", [leaf("A", 0.1), leaf("B", 0.2)])
    result = cutsets.compute(tree, None, NO_LIMITS)
    assert ids(result) == [["A"], ["B"]]
    assert result["nonCoherent"] is True
    assert [a["code"] for a in result["approximations"]] == ["NONCOHERENT_XOR"]


def test_pand_is_and_and_listed():
    tree = gate("root", "PAND", [leaf("A", 0.1), leaf("B", 0.2)])
    result = cutsets.compute(tree, None, NO_LIMITS)
    assert ids(result) == [["A", "B"]]
    assert "PAND_APPROX" in [a["code"] for a in result["approximations"]]
    assert result["treeWalk"] == pytest.approx(0.01)


def test_transfer_missing_and_cycle():
    tree = gate("root", "OR", [gate("t", "TRANSFER", [], transferTo="nowhere"),
                               leaf("A", 0.1)])
    result = cutsets.compute(tree, None, NO_LIMITS)
    assert ids(result) == [["A"]]
    assert [w["code"] for w in result["warnings"]] == ["TRANSFER_MISSING"]

    loop = gate("root", "OR", [gate("t1", "TRANSFER", [], transferTo="t2"),
                               gate("t2", "TRANSFER", [], transferTo="t1"),
                               leaf("A", 0.1)])
    result = cutsets.compute(loop, None, NO_LIMITS)
    assert ids(result) == [["A"]]
    assert "TRANSFER_CYCLE" in [w["code"] for w in result["warnings"]]


def test_link_cycle_mirrors_the_engine():
    # g links to root (AND): root is on the stack without a gate-only value.
    tree = gate("root", "OR", [gate("g", "AND", [leaf("A", 0.1), leaf("B", 0.2)],
                                    links=[{"target_id": "root", "relation": "AND"}]),
                               leaf("C", 0.3)])
    result = cutsets.compute(tree, None, NO_LIMITS)
    assert ids(result) == [["A", "B"], ["C"]]
    assert "CYCLIC_LINK" in [w["code"] for w in result["warnings"]]


# ---- truncation ---------------------------------------------------------------------------


def _wide_tree():
    return gate("root", "OR", [
        leaf("A", 0.1),
        gate("g", "AND", [leaf("B", 0.01), leaf("C", 0.02)]),
        gate("h", "AND", [leaf("D", 1e-6), leaf("E", 1e-6), leaf("F", 0.5)]),
    ])


def test_truncation_by_order():
    result = cutsets.compute(_wide_tree(), None, {"maxOrder": 2, "maxCount": 100, "cutoff": 0})
    assert ids(result) == [["A"], ["B", "C"]]
    assert result["truncated"] is True and result["truncatedBy"] == ["order"]
    assert result["warnings"][-1]["code"] == "CUTSETS_TRUNCATED"


def test_truncation_by_cutoff():
    result = cutsets.compute(_wide_tree(), None, {"maxOrder": 6, "maxCount": 100, "cutoff": 1e-6})
    assert ids(result) == [["A"], ["B", "C"]]
    assert result["truncatedBy"] == ["cutoff"]


def test_truncation_by_count():
    result = cutsets.compute(_wide_tree(), None, {"maxOrder": 6, "maxCount": 2, "cutoff": 0})
    assert ids(result) == [["A"], ["B", "C"]]
    assert result["truncatedBy"] == ["count"]


def test_no_truncation_flags_when_nothing_dropped():
    result = cutsets.compute(_wide_tree(), None, NO_LIMITS)
    assert result["truncated"] is False and result["truncatedBy"] == []
    assert result["total"] == 3
    assert [cs["rank"] for cs in result["cutSets"]] == [1, 2, 3]
    probs = [cs["probability"] for cs in result["cutSets"]]
    assert probs == sorted(probs, reverse=True)
    assert sum(cs["share"] for cs in result["cutSets"]) == pytest.approx(1.0)


def test_limits_default_from_analysis():
    analysis = engine.default_analysis()
    analysis["cutsets"]["maxOrder"] = 1
    result = cutsets.compute(_wide_tree(), analysis)
    assert ids(result) == [["A"]] and result["limits"]["maxOrder"] == 1


def test_input_tree_is_not_modified():
    tree = _wide_tree()
    before = copy.deepcopy(tree)
    cutsets.compute(tree, None)
    assert tree == before


# ---- brute force against the engine --------------------------------------------------------


def random_tree(rng, max_events=12):
    counter = itertools.count()
    all_nodes = []
    events = []

    def build(depth):
        nid = "n%d" % next(counter)
        node = {"id": nid, "name": nid, "links": []}
        all_nodes.append(node)
        n_children = rng.choice([0, 0, 1, 2, 3]) if depth < 4 else 0
        if depth == 0:
            n_children = rng.choice([2, 3])
        if n_children and len(events) < max_events:
            kind = rng.choice(["AND", "OR", "OR", "KOFN", "INHIBIT", "LEGACY"])
            if kind == "LEGACY":
                node["logicGate"] = rng.choice(["AND", "OR", "and", "", None])
            else:
                node["logicGate"] = "AND" if kind in ("AND", "INHIBIT") else "OR"
                node["gateType"] = kind
                if kind == "KOFN":
                    node["k"] = rng.choice([1, 2, 2, 3, 5])
            node["children"] = [build(depth + 1) for _ in range(n_children)]
        else:
            node["children"] = []
            r = rng.random()
            if r < 0.1:
                node["eventKind"] = "house"
                node["houseState"] = rng.random() < 0.5
            elif r < 0.2:
                node["gateType"] = "TRANSFER"  # target chosen below
            else:
                node["probability"] = round(rng.uniform(0.01, 0.6), 3)
                if rng.random() < 0.2:
                    node["eventKind"] = rng.choice(["undeveloped", "conditioning"])
                events.append(node)
        return node

    root = build(0)
    root["id"] = "root"
    for node in all_nodes:
        if node.get("gateType") == "TRANSFER":
            if rng.random() < 0.1:
                node["transferTo"] = "missing"
            else:
                node["transferTo"] = rng.choice(all_nodes)["id"]
        if rng.random() < 0.2:
            node["links"].append({"target_id": rng.choice(all_nodes)["id"],
                                  "relation": rng.choice(["AND", "OR"])})
    return root


def truth(structure_events, tree):
    """Minimal true assignments of the engine's structure function, as sorted
    id lists, plus the exact top probability."""
    core = WebCore()
    core.set_data(copy.deepcopy(tree))
    by_id = {}
    for node in core._walk(core.get_data()):
        by_id.setdefault(str(node.get("id")), node)
    event_ids = [e["id"] for e in structure_events]
    qs = [e["q"] for e in structure_events]
    true_masks = []
    exact = 0.0
    for mask in range(1 << len(event_ids)):
        for i, eid in enumerate(event_ids):
            by_id[eid]["probability"] = 1.0 if mask >> i & 1 else 0.0
        core.recalculate_probabilities()
        value = core.get_data()["calculatedProbability"]
        assert value in (0.0, 1.0)
        if value == 1.0:
            true_masks.append(mask)
            w = 1.0
            for i in range(len(event_ids)):
                w *= qs[i] if mask >> i & 1 else 1.0 - qs[i]
            exact += w
    true_set = set(true_masks)
    minimal = []
    for m in true_masks:
        # minimal iff no true proper subset obtained by removing one bit
        # (monotone function: checking single-bit removals suffices)
        if all((m & ~(1 << i)) not in true_set for i in range(len(event_ids)) if m >> i & 1):
            minimal.append(sorted(event_ids[i] for i in range(len(event_ids)) if m >> i & 1))
    return sorted(minimal), exact


@pytest.mark.parametrize("seed", range(220))
def test_cutsets_match_brute_force(seed):
    rng = random.Random(seed)
    tree = random_tree(rng)
    structure = logic.compile_tree(tree, None)
    if len(structure.events) > 12:
        pytest.skip("too many events for brute force")
    # The graph reproduces the tree walk exactly.
    core = WebCore()
    core.set_data(copy.deepcopy(tree))
    core.recalculate_probabilities()
    walk = core.get_data()["calculatedProbability"]
    assert structure.evaluate() == pytest.approx(walk, rel=1e-9, abs=1e-12)

    result = cutsets.compute(tree, None, NO_LIMITS, structure=structure)
    expected, exact = truth(structure.events, tree)
    assert ids(result) == expected
    # Minimality: no cut set contains another.
    sets = [frozenset(x) for x in ids(result)]
    for a in sets:
        for b in sets:
            assert a is b or not a < b
    assert result["treeWalk"] == pytest.approx(walk)
    if not result["repeatedEvents"]:
        # No repeated events: the tree walk is the exact probability.
        assert walk == pytest.approx(exact, rel=1e-9, abs=1e-12)
    # MCUB is an upper bound of the exact value, rare-event above MCUB.
    assert result["mcub"] >= exact - 1e-12
    assert result["rareEvent"] >= result["mcub"] - 1e-12


def test_brute_force_corpus_has_the_interesting_cases():
    """Keep the random generator honest: the 220 seeds above must exercise
    repeated events, KOFN, transfers, links and house events."""
    seen = {"repeated": 0, "kofn": 0, "transfer": 0, "link": 0, "house": 0}
    for seed in range(220):
        tree = random_tree(random.Random(seed))
        s = logic.compile_tree(tree, None)
        if len(s.events) > 12:
            continue
        seen["repeated"] += bool(s.repeated)
        nodes = list(WebCore._walk(tree))
        seen["kofn"] += any(n.get("gateType") == "KOFN" for n in nodes)
        seen["transfer"] += any(n.get("gateType") == "TRANSFER" for n in nodes)
        seen["link"] += any(n.get("links") for n in nodes)
        seen["house"] += any(n.get("eventKind") == "house" for n in nodes)
    assert all(count >= 20 for count in seen.values()), seen


# ---- summary -----------------------------------------------------------------------------


def test_summary_headline_uses_mcub_with_repeated_events():
    tree = gate("root", "OR", [
        gate("g1", "AND", [leaf("A", 0.5), leaf("B", 0.5)]),
        gate("g2", "AND", [gate("t", "TRANSFER", [], transferTo="A"), leaf("C", 0.5)]),
    ])
    out = engine.summary(tree, None)
    assert out["headlineMethod"] == "mcub"
    assert out["headline"] == out["mcub"] == pytest.approx(1 - 0.75 * 0.75)
    assert out["treeWalk"] == pytest.approx(1 - 0.75 * 0.75)
    assert out["rareEvent"] == pytest.approx(0.5)
    assert out["repeatedEvents"] == [{"id": "A", "name": "A"}]
    assert out["truncated"] is False and "elapsedMs" in out


def test_summary_tree_walk_without_repeats():
    tree = gate("root", "OR", [leaf("A", 0.5), leaf("B", 0.5)])
    out = engine.summary(tree, None)
    assert out["headlineMethod"] == "treeWalk" and out["headline"] == 0.75
    assert out["mcub"] == pytest.approx(0.75) and out["rareEvent"] == pytest.approx(1.0)


def test_summary_falls_back_to_tree_walk_on_error():
    tree = gate("root", "KOFN", [leaf("e%d" % i, 0.01) for i in range(30)], k=10)
    out = engine.summary(tree, None)
    assert out["truncated"] is True
    assert out["headlineMethod"] == "treeWalk"
    assert out["headline"] == out["treeWalk"]
    assert out["headline"] == pytest.approx(
        engine.kofn_probability([0.01] * 30, 10), rel=1e-6)


def test_summary_xor_is_mcub_and_non_coherent():
    tree = gate("root", "XOR", [leaf("A", 0.5), leaf("B", 0.5)])
    out = engine.summary(tree, None)
    assert out["nonCoherent"] is True and out["headlineMethod"] == "mcub"
    assert out["treeWalk"] == pytest.approx(0.5)
    assert out["headline"] == pytest.approx(0.75)


def test_quant_models_feed_the_cut_sets():
    tree = gate("root", "OR", [leaf("A", 0.0, quant={"model": "rate", "lambda": 1e-4}),
                               leaf("B", 0.1)])
    result = cutsets.compute(tree, {"missionTime": 100})
    q = {e["id"]: e["q"] for cs in result["cutSets"] for e in cs["events"]}
    assert q["A"] == pytest.approx(-math.expm1(-1e-2))


# ---- the MCUB: accurate, and the same bits on every Python build ---------------------------


def _exact_mcub(probs):
    from fractions import Fraction

    prod = Fraction(1)
    for p in probs:
        prod *= 1 - Fraction(p)
    return float(1 - prod)


@pytest.mark.parametrize("seed", range(30))
def test_mcub_matches_exact_rational_arithmetic(seed):
    rng = random.Random(seed)
    probs = sorted((rng.choice([0.5, 0.1, 1e-3, 1e-7, 1e-12, 1e-18]) * rng.uniform(0.5, 1.5)
                    for _ in range(rng.randint(1, 400))), reverse=True)
    assert cutsets.mcub_of(probs) == pytest.approx(_exact_mcub(probs), rel=1e-13, abs=0)


def test_mcub_edge_cases():
    assert cutsets.mcub_of([]) == 0.0 and str(cutsets.mcub_of([])) == "0.0"
    assert cutsets.mcub_of([0.3, 1.0, 0.2]) == 1.0
    assert cutsets.mcub_of([0.0, 0.0]) == 0.0
    assert cutsets.mcub_of([1e-18, 1e-18]) == pytest.approx(2e-18, rel=1e-15, abs=0)


def test_headline_numbers_do_not_use_libm(monkeypatch):
    """log1p/expm1/exp differ in the last bit between Python builds (the
    3.14 exe vs a 3.10 venv: expm1(-0.030149) is ...917 vs ...913), which
    made the same file's MCUB headline differ in its last digit between the
    two. The MCUB and the engine's small-OR branch use + - * only, so a
    fixed-probability tree gives the same bits on every build."""
    def boom(*_args):
        raise AssertionError("libm used")

    tree = gate("root", "OR", [gate("g", "AND", [leaf("A", 1e-9), leaf("B", 2e-9)]),
                               leaf("C", 3e-9)])
    tree["children"][0]["links"] = [{"target_id": "C", "relation": "OR"}]
    for name in ("log1p", "expm1", "exp", "log"):
        monkeypatch.setattr(math, name, boom)
    assert cutsets.mcub_of([0.1, 1e-17, 3e-9]) > 0
    assert engine.or_probability([1e-17, 2e-17]) == pytest.approx(3e-17, rel=1e-15, abs=0)
    core = WebCore()
    core.set_data(copy.deepcopy(tree))
    core.recalculate_probabilities()
    summary = engine.summary(core.get_data(), core.analysis)
    assert summary["headlineMethod"] == "mcub" and summary["headline"] > 0
