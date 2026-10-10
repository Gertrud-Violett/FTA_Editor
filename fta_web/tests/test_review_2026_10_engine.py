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
