"""A leaf with links is a gate for the CCF gate values (F2 R1, FN-66).

The acceptance tests in ``acceptance/ccf`` judge a leaf with an AND link and a
member with an AND link; these check what they do not: an OR link, a link to a
transfer gate, a leaf with links that has no member below it, and a file without
groups. Expected numbers are derived by hand in the comments.
"""
import pytest

from fta_web import ccf, engine, logic

QT = 1e-3
BETA = 0.1
INDEPENDENT = (1 - BETA) * QT  # 9e-4: the independent part of a member
CCF_EVENT = BETA * QT  # 1e-4: the CCF event of the pair


def leaf(node_id, q=QT, **extra):
    node = {"id": node_id, "name": "Pump " + node_id, "type": "Event", "logicGate": "OR",
            "probability": q, "notes": "", "links": [], "children": []}
    node.update(extra)
    return node


def gate(node_id, kind, children):
    return leaf(node_id, 0.0, name="Gate " + node_id, logicGate=kind, gateType=kind,
                children=children)


def top(*children):
    return {"id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "probability": 1.0,
            "notes": "", "links": [], "children": list(children)}


def link(target, relation):
    return {"target_id": target, "relation": relation}


def analysis(members=("A", "B")):
    return {"ccfGroups": [ccf.make_group("g1", "Feed", BETA, members, "src")]}


def mcub(*qs):
    """1 - prod(1 - q): the min-cut upper bound of cut sets with these probabilities."""
    rest = 1.0
    for q in qs:
        rest *= 1.0 - q
    return 1.0 - rest


def test_a_leaf_with_an_or_link_to_a_member_shows_the_mcub_of_its_expansion():
    # X = X OR A; A = A' OR C. X's cut sets: {X}, {A'}, {C}.
    tree = top(gate("G1", "OR", [leaf("A"), leaf("B")]), leaf("X", 0.01, links=[link("A", "OR")]))
    out = engine.summary(tree, analysis())
    gates = out["ccfGates"]
    assert set(gates) == {"G1", "X", "root"}
    assert gates["X"]["method"] == "mcub"
    assert gates["X"]["value"] == pytest.approx(mcub(0.01, INDEPENDENT, CCF_EVENT), rel=1e-9)
    # the tree walk is 1 - (1 - 0.01)(1 - Q_t), which is not the same number
    assert gates["X"]["value"] != pytest.approx(mcub(0.01, QT), rel=1e-6)
    assert "A" not in gates and "B" not in gates


def test_a_leaf_with_an_or_link_to_a_transfer_gate_shows_the_mcub_of_the_target():
    # T transfers to G1 = OR[A, B]; X = X OR T. X's cut sets: {X}, {A'}, {B'}, {C}.
    tree = top(gate("G1", "OR", [leaf("A"), leaf("B")]),
               leaf("T", 0.0, gateType="TRANSFER", transferTo="G1"),
               leaf("X", 0.01, links=[link("T", "OR")]))
    gates = engine.summary(tree, analysis())["ccfGates"]
    assert set(gates) == {"G1", "T", "X", "root"}
    expected = mcub(0.01, INDEPENDENT, INDEPENDENT, CCF_EVENT)
    assert gates["X"]["value"] == pytest.approx(expected, rel=1e-9)
    assert gates["T"]["value"] == pytest.approx(mcub(INDEPENDENT, INDEPENDENT, CCF_EVENT), rel=1e-9)


def test_a_leaf_with_links_and_no_member_below_it_is_not_a_gate():
    tree = top(gate("G1", "OR", [leaf("A"), leaf("B")]), leaf("C", 0.2),
               leaf("X", 0.01, links=[link("C", "AND")]))
    gates = engine.summary(tree, analysis())["ccfGates"]
    assert set(gates) == {"G1", "root"}  # X and C are plain events with an ordinary value


def test_a_leaf_with_a_dangling_link_stays_a_plain_event():
    tree = top(gate("G1", "OR", [leaf("A"), leaf("B")]),
               leaf("X", 0.01, links=[link("nowhere", "AND")]))
    assert set(engine.summary(tree, analysis())["ccfGates"]) == {"G1", "root"}


def test_node_ops_lists_a_leaf_with_links_and_never_a_bare_member_or_event():
    tree = top(gate("G1", "OR", [leaf("A"), leaf("B")]), leaf("C", 0.2),
               leaf("X", 0.01, links=[link("A", "AND")]), leaf("A2"))
    structure = logic.compile_tree(tree, analysis())
    assert set(structure.node_ops) == {"G1", "X", "root"}
    assert structure.ccf_flag[structure.node_ops["X"]] is True


def test_without_groups_no_node_is_a_gate_value_and_nothing_changes():
    tree = top(gate("G1", "OR", [leaf("A"), leaf("B")]), leaf("X", 0.01, links=[link("A", "AND")]))
    structure = logic.compile_tree(tree, {})
    assert structure.node_ops == {} and structure.ccf_flag == []
    assert "ccfGates" not in engine.summary(tree, {})


def test_substitute_gate_values_writes_the_text_of_a_leaf_with_links_only():
    tree = top(leaf("A"), leaf("X", 0.01, links=[link("A", "AND")]))
    for node in tree["children"]:
        node["calculatedProbability"] = 0.5
    ccf.substitute_gate_values(tree, {"X": {"method": "mcub", "value": 1.5e-5},
                                      "root": {"method": "na"}})
    a, x = tree["children"]
    assert a["calculatedProbability"] == 0.5  # a bare leaf keeps its value
    assert x["calculatedProbability"] == "1.5e-05 (MCUB, CCF)"
    assert tree["calculatedProbability"] == ccf.NA_TEXT
