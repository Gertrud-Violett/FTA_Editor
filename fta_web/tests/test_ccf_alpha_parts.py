"""``alphaParts`` of a group item of ``ccf.listing`` (F2A rework R1).

The Details panel shows these numbers for a member of an applied alpha group, so
they must be exactly what ``ccf.event_probabilities`` gives the expansion and the
diagram (one probability function, FN-19), and only an applied alpha group has
them.
"""
import itertools

import pytest

from fta_web import ccf

ALPHA = [0.955, 0.034, 0.011]
QT = 1e-3


def leaf(node_id):
    return {"id": node_id, "name": "Valve " + node_id, "type": "Event", "logicGate": "OR",
            "probability": QT, "notes": "", "links": [], "children": []}


def tree():
    return {"id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "probability": 1.0,
            "notes": "", "links": [], "children": [leaf("A"), leaf("B"), leaf("C")]}


def alpha_group(testing, gid="g1"):
    return ccf.make_group(gid, "Valves", None, ["A", "B", "C"], "", model="alpha",
                          alpha=list(ALPHA), testing=testing)


@pytest.mark.parametrize("testing", ["staggered", "nonStaggered"])
def test_an_applied_alpha_group_carries_the_numbers_of_event_probabilities(testing):
    items, _block = ccf.listing(tree(), {"ccfGroups": [alpha_group(testing)]}, "FTA")
    assert items[0]["status"]["applied"] is True
    parts = items[0]["alphaParts"]
    expected = ccf.event_probabilities("alpha", {"alpha": ALPHA, "testing": testing}, [QT] * 3)
    assert parts["independent"] == pytest.approx(list(expected.independent), rel=1e-12, abs=0)
    assert len(parts["events"]) == len(expected.events) == 4
    names = ["Valve A", "Valve B", "Valve C"]
    ids = ["A", "B", "C"]
    # size ascending, then in group order: A+B, A+C, B+C, A+B+C
    subsets = [s for k in (2, 3) for s in itertools.combinations(range(3), k)]
    for event, (idxs, q), subset in zip(parts["events"], expected.events, subsets):
        assert tuple(idxs) == subset
        assert event["members"] == [ids[i] for i in subset]
        assert event["memberNames"] == [names[i] for i in subset]
        assert event["q"] == pytest.approx(q, rel=1e-12, abs=0)


def test_the_numbers_are_the_ones_of_the_formulas():
    # S1 Eq. 5.6 p. 40 (staggered): Q_1 = alpha_1 Q_t = 9.55e-4; Q_2 = alpha_2 / 2 Q_t = 1.7e-5; Q_3 = alpha_3 Q_t = 1.1e-5
    items, _block = ccf.listing(tree(), {"ccfGroups": [alpha_group("staggered")]}, "FTA")
    parts = items[0]["alphaParts"]
    assert parts["independent"][0] == pytest.approx(9.55e-4, rel=1e-12, abs=0)
    assert [e["q"] for e in parts["events"]] == pytest.approx([1.7e-5] * 3 + [1.1e-5], rel=1e-12, abs=0)
    # S1 Eq. 5.7-5.9 p. 41 (non-staggered), alpha_t = 1.056: Q_1 = alpha_1 / alpha_t Q_t
    items, _block = ccf.listing(tree(), {"ccfGroups": [alpha_group("nonStaggered")]}, "FTA")
    assert items[0]["alphaParts"]["independent"][0] == pytest.approx(0.955 / 1.056 * QT, rel=1e-12, abs=0)


def test_a_beta_group_has_no_alpha_parts():
    beta = ccf.make_group("g2", "Feed", 0.1, ["A", "B"], "src")
    items, _block = ccf.listing(tree(), {"ccfGroups": [beta]}, "FTA")
    assert items[0]["status"]["applied"] is True
    assert "alphaParts" not in items[0]


def test_an_alpha_group_that_is_not_applied_has_no_alpha_parts():
    items, _block = ccf.listing(tree(), {"ccfGroups": [alpha_group(None)]}, "FTA")  # no testing scheme
    assert items[0]["status"]["applied"] is False
    assert "alphaParts" not in items[0]
    items, _block = ccf.listing(tree(), {"ccfGroups": [alpha_group("staggered")]}, "ETA")  # event trees apply no group
    assert items[0]["status"]["applied"] is False
    assert "alphaParts" not in items[0]
