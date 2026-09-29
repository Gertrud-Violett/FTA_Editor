"""
Tests for ``fta_web.lint``: one fixture per issue code, the clean tree, the
sample file, FTA/ETA separation, severities, ordering, de-duplication and speed.
"""
import copy
import json
import random
import re
import time
from pathlib import Path

import pytest

from fta_web import lint

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "fta_web" / "examples" / "sampleFTA.json"
VAL_JS = REPO_ROOT / "fta_web" / "static" / "js" / "i18n" / "val.js"


# ---- tiny tree builders -----------------------------------------------------------------


def leaf(nid, p=0.1, **extra):
    return dict({"id": nid, "name": "N" + nid, "type": "Event", "probability": p,
                 "logicGate": "OR", "children": [], "links": []}, **extra)


def gate(nid, children, gate_="OR", p=1.0, **extra):
    return dict({"id": nid, "name": "G" + nid, "type": "Event", "probability": p,
                 "logicGate": gate_, "children": children, "links": []}, **extra)


def top(*children, gate_="OR"):
    node = gate("root", list(children), gate_)
    node["type"] = "Root"
    return node


def clean():
    """A small tree with no issues at all."""
    return top(
        gate("g1", [leaf("a", 0.1), leaf("b", 0.2)], "AND"),
        leaf("c", 0.3, links=[{"target_id": "a", "relation": "OR"}]),
    )


def codes(issues):
    return [i["code"] for i in issues]


def only(issues, code):
    found = [i for i in issues if i["code"] == code]
    assert found, "expected %s in %s" % (code, codes(issues))
    return found


# ---- clean trees -------------------------------------------------------------------------


def test_clean_tree_has_no_issues():
    assert lint.run(clean(), None) == []


def test_fresh_document_has_no_issues():
    fresh = {"id": "root", "name": "RootEvent", "type": "Root", "logicGate": "",
             "probability": 1.0, "children": [], "links": [], "notes": ""}
    assert lint.run(fresh, None) == []
    assert lint.run(fresh, None, mode="ETA") == []


def test_sample_file_triggers_only_warnings():
    """The shipped example: no errors (``fta_editor validate`` must exit 0),
    and exactly these warnings -- asserted so a rule change is noticed."""
    tree = json.loads(SAMPLE.read_text(encoding="utf-8"))["tree"]
    issues = lint.run(tree, None)
    assert lint.counts(issues) == {"error": 0, "warning": 14, "info": 0}
    by_code = {}
    for issue in issues:
        by_code.setdefault(issue["code"], []).append(issue["nodeId"])
    assert by_code == {
        "SINGLE_INPUT_GATE": ["root_0_1", "root_3", "root_4"],
        "PARENT_PROBABILITY_IGNORED": ["root_0", "root_0_1", "root_2", "root_4"],
        "DEFAULT_PROBABILITY": ["root_0_1_0", "root_0_3", "root_1_0_1", "root_2_0",
                                "root_2_2", "root_4_0", "root_5"],
    }


def test_run_does_not_modify_its_inputs():
    tree = top(leaf("a", 1.0), gate("g", [leaf("b")], p=0.5))
    snapshot = copy.deepcopy(tree)
    warnings = [{"severity": "warning", "code": "LOAD_REPAIR", "nodeId": "a",
                 "message": "m", "params": {"kind": "x"}}]
    before = copy.deepcopy(warnings)
    lint.run(tree, {"missionTime": 10}, warnings)
    assert tree == snapshot and warnings == before


def test_malformed_input_does_not_raise():
    assert lint.run(None, None) == []
    assert lint.run({}, None) == []
    issues = lint.run({"id": "root", "children": [{"id": "x", "probability": "junk"}]}, None)
    assert isinstance(issues, list)


# ---- one fixture per code ------------------------------------------------------------------


def test_dangling_link():
    tree = top(leaf("a", links=[{"target_id": "ghost", "relation": "AND"}]), leaf("b"))
    issue = only(lint.run(tree, None), "DANGLING_LINK")[0]
    assert issue["severity"] == "error" and issue["nodeId"] == "a"
    assert issue["params"] == {"targetId": "ghost", "relation": "AND"}
    assert "ghost" in issue["message"]


def test_cyclic_link_to_an_ancestor():
    tree = top(gate("g", [leaf("a", links=[{"target_id": "g", "relation": "OR"}]), leaf("b")]))
    issue = only(lint.run(tree, None), "CYCLIC_LINK")[0]
    assert issue["severity"] == "warning"
    assert issue["nodeId"] == "a" and issue["params"]["targetId"] == "g"


def test_cyclic_links_between_siblings_and_self():
    tree = top(
        leaf("a", links=[{"target_id": "b", "relation": "OR"}]),
        leaf("b", links=[{"target_id": "a", "relation": "OR"}]),
        leaf("c", links=[{"target_id": "c", "relation": "OR"}]),
        leaf("d", links=[{"target_id": "a", "relation": "OR"}]),  # into the loop, not part of it
    )
    assert [i["nodeId"] for i in only(lint.run(tree, None), "CYCLIC_LINK")] == ["a", "b", "c"]


def test_transfer_missing():
    tree = top(gate("t", [], gateType="TRANSFER", transferTo="nowhere"), leaf("b"))
    issue = only(lint.run(tree, None), "TRANSFER_MISSING")[0]
    assert issue["severity"] == "error" and issue["nodeId"] == "t"
    assert issue["params"]["transferTo"] == "nowhere"


def test_transfer_cycle():
    tree = top(gate("g", [gate("t", [], gateType="TRANSFER", transferTo="g"), leaf("b")]))
    issue = only(lint.run(tree, None), "TRANSFER_CYCLE")[0]
    assert issue["severity"] == "error" and issue["nodeId"] == "t"


def test_transfer_has_children():
    tree = top(gate("t", [leaf("x"), leaf("y")], gateType="TRANSFER", transferTo="b"), leaf("b"))
    issues = lint.run(tree, None)
    issue = only(issues, "TRANSFER_HAS_CHILDREN")[0]
    assert issue["severity"] == "warning" and issue["params"] == {"n": 2}
    # Children are ignored, so the gate's own probability is not "ignored" too.
    assert "PARENT_PROBABILITY_IGNORED" not in codes(issues)


def test_house_has_children():
    tree = top(gate("h", [leaf("x"), leaf("y")], eventKind="house", houseState=True), leaf("b"))
    issue = only(lint.run(tree, None), "HOUSE_HAS_CHILDREN")[0]
    assert issue["severity"] == "warning" and issue["nodeId"] == "h"


def test_house_leaf_at_one_is_not_default_probability():
    tree = top(leaf("h", 1.0, eventKind="house", houseState=True), leaf("b"))
    assert lint.run(tree, None) == []


@pytest.mark.parametrize("children", [
    [leaf("x")],                                               # no conditioning event
    [leaf("x"), leaf("y")],                                    # two inputs, none conditioning
    [leaf("x"), leaf("c", eventKind="conditioning"), leaf("z")],  # three children
])
def test_inhibit_arity(children):
    tree = top(gate("i", children, "AND", gateType="INHIBIT"), leaf("b"))
    issue = only(lint.run(tree, None), "INHIBIT_ARITY")[0]
    assert issue["severity"] == "error" and issue["nodeId"] == "i"


def test_inhibit_well_formed():
    tree = top(gate("i", [leaf("x"), leaf("c", 0.5, eventKind="conditioning")], "AND",
                    gateType="INHIBIT"), leaf("b"))
    assert lint.run(tree, None) == []


@pytest.mark.parametrize("k", [None, 0, 4, "2"])
def test_kofn_arity(k):
    extra = {"gateType": "KOFN"}
    if k is not None:
        extra["k"] = k
    tree = top(gate("v", [leaf("x"), leaf("y"), leaf("z")], **extra), leaf("b"))
    issues = only(lint.run(tree, None), "KOFN_ARITY")
    assert len(issues) == 1  # the engine's own KOFN_ARITY is de-duplicated
    assert issues[0]["severity"] == "error" and issues[0]["params"]["n"] == 3


def test_kofn_well_formed():
    tree = top(gate("v", [leaf("x"), leaf("y"), leaf("z")], gateType="KOFN", k=2), leaf("b"))
    assert lint.run(tree, None) == []


def test_xor_arity_and_noncoherent():
    tree = top(gate("x", [leaf("p"), leaf("q"), leaf("r")], gateType="XOR"),
               gate("y", [leaf("s"), leaf("t")], gateType="XOR"))
    issues = lint.run(tree, None)
    arity = only(issues, "XOR_ARITY")
    assert len(arity) == 1 and arity[0]["nodeId"] == "x" and arity[0]["severity"] == "error"
    nc = only(issues, "NONCOHERENT_XOR")
    assert len(nc) == 1 and nc[0]["severity"] == "warning"
    assert nc[0]["nodeId"] == "x" and nc[0]["params"] == {"count": 2, "nodeIds": ["x", "y"]}


def test_quant_param_missing():
    tree = top(leaf("r", 0.2, quant={"model": "rate"}), leaf("b"))
    issue = only(lint.run(tree, {"missionTime": 100}), "QUANT_PARAM_MISSING")[0]
    assert issue["severity"] == "error" and issue["nodeId"] == "r"
    assert issue["params"] == {"model": "rate", "missing": ["lambda"]}
    assert "lambda" in issue["message"]


def test_rate_model_leaf_at_one_is_not_default_probability():
    tree = top(leaf("r", 1.0, quant={"model": "rate", "lambda": 1e-5}), leaf("b"))
    assert lint.run(tree, None) == []


def test_single_input_gate():
    tree = top(gate("g", [leaf("a")], "AND"), leaf("b"))
    issue = only(lint.run(tree, None), "SINGLE_INPUT_GATE")[0]
    assert issue["severity"] == "warning" and issue["params"] == {"gate": "AND"}


def test_single_input_gate_exemptions():
    # A link makes it a real combination; the top event is exempt.
    linked = top(gate("g", [leaf("a")], links=[{"target_id": "b", "relation": "AND"}]), leaf("b"))
    assert "SINGLE_INPUT_GATE" not in codes(lint.run(linked, None))
    assert lint.run(top(leaf("a")), None) == []


def test_default_probability():
    tree = top(leaf("a", 1.0), leaf("b"))
    issue = only(lint.run(tree, None), "DEFAULT_PROBABILITY")[0]
    assert issue["severity"] == "warning" and issue["nodeId"] == "a"
    missing = top(leaf("a"), leaf("b"))
    del missing["children"][0]["probability"]
    assert "DEFAULT_PROBABILITY" in codes(lint.run(missing, None))


def test_parent_probability_ignored():
    tree = top(gate("g", [leaf("a", 0.1), leaf("b", 0.2)], "AND", p=0.5), leaf("c"))
    issue = only(lint.run(tree, None), "PARENT_PROBABILITY_IGNORED")[0]
    assert issue["severity"] == "warning" and issue["nodeId"] == "g"
    assert issue["params"]["probability"] == 0.5
    assert issue["params"]["calculated"] == pytest.approx(0.02)
    # Equal to the calculated value (a tree saved by 1.7) is fine.
    tree["children"][0]["probability"] = 0.02
    assert "PARENT_PROBABILITY_IGNORED" not in codes(lint.run(tree, None))


def test_standby_large_lambda_tau():
    tree = top(leaf("s", 0.1, quant={"model": "standby", "lambda": 1e-2, "tau": 50}), leaf("b"))
    issue = only(lint.run(tree, None), "STANDBY_LARGE_LT")[0]
    assert issue["severity"] == "warning" and issue["params"]["lambdaTau"] == pytest.approx(0.5)


def test_rate_implausible_flags_fit_values_entered_per_hour():
    # 120 and 45 FIT imported as /h: q = 1 for both, MTBF of minutes.
    tree = top(leaf("r", 1.0, quant={"model": "rate", "lambda": 120.0}),
               leaf("s", 1.0, quant={"model": "standby", "lambda": 45.0, "tau": 730.0}),
               leaf("m", 1.0, quant={"model": "repairable", "lambda": 0.05, "mttr": 8.0}))
    issues = only(lint.run(tree, None), "RATE_IMPLAUSIBLE")
    assert [i["nodeId"] for i in issues] == ["r", "s", "m"]
    first = issues[0]
    assert first["severity"] == "warning"
    assert first["params"] == {"lambda": 120.0, "unit": "h", "q": 1.0, "model": "rate"}
    assert first["message"] == ("Failure rate λ = 120/h looks implausibly high (q = 1). "
                                "Check the unit (FIT = 1e-9/h, /y = /8760 h).")
    assert issues[2]["params"]["q"] == pytest.approx(0.05 / (0.05 + 1 / 8.0))


def test_rate_implausible_q_near_one_from_a_long_mission():
    # λ = 1e-3/h is plausible on its own; over 10,000 h the event is certain.
    tree = top(leaf("r", 0.5, quant={"model": "rate", "lambda": 1e-3, "T": 10000.0}), leaf("b"))
    issue = only(lint.run(tree, None), "RATE_IMPLAUSIBLE")[0]
    assert issue["params"]["q"] >= 0.999 and issue["params"]["lambda"] == 1e-3
    # ... and the mission time counts when T is not set.
    tree = top(leaf("r", 0.5, quant={"model": "rate", "lambda": 1e-3}), leaf("b"))
    assert "RATE_IMPLAUSIBLE" in codes(lint.run(tree, {"missionTime": 10000.0}))
    assert "RATE_IMPLAUSIBLE" not in codes(lint.run(tree, {"missionTime": 100.0}))


def test_rate_implausible_boundaries_and_exemptions():
    ok = top(
        leaf("a", 0.5, quant={"model": "rate", "lambda": 1e-6}),
        leaf("b", 0.5, quant={"model": "standby", "lambda": 1e-2, "tau": 10.0}),  # == limit
        leaf("c", 0.5, quant={"model": "rate", "T": 100.0}),        # λ missing: not this rule
        leaf("d", 0.5, quant={"model": "fixed", "lambda": 50.0}),   # fixed ignores λ
        leaf("e", 0.5, eventKind="house", houseState=True,
             quant={"model": "rate", "lambda": 50.0}),              # a house is a switch
    )
    found = codes(lint.run(ok, None))
    assert "RATE_IMPLAUSIBLE" not in found
    assert "QUANT_PARAM_MISSING" in found
    assert "RATE_IMPLAUSIBLE" not in codes(lint.run(
        top(leaf("r", 1.0, quant={"model": "rate", "lambda": 120.0})), None, mode="ETA"))


def test_cutsets_truncated_only_when_passed_in():
    assert "CUTSETS_TRUNCATED" not in codes(lint.run(clean(), None))
    assert lint.run(clean(), None, extra={"cutsets": {"truncated": False}}) == []
    issues = lint.run(clean(), None, extra={"cutsets": {"truncated": True,
                                                        "truncatedBy": ["maxOrder"],
                                                        "count": 7}})
    issue = only(issues, "CUTSETS_TRUNCATED")[0]
    assert issue["severity"] == "warning" and issue["nodeId"] is None
    assert issue["params"] == {"reason": "maxOrder", "count": 7}


def test_eta_branch_sum():
    tree = top(gate("s", [leaf("y", 0.9), leaf("n", 0.1)]), leaf("f", 0.3))
    tree["probability"] = 1.0
    issues = lint.run(tree, None, mode="ETA")
    issue = only(issues, "ETA_BRANCH_SUM")[0]
    assert issue["severity"] == "warning" and issue["nodeId"] == "root"
    assert issue["params"]["sum"] == pytest.approx(1.3)
    assert codes(issues) == ["ETA_BRANCH_SUM"]


def test_undeveloped_event():
    tree = top(leaf("u", 0.01, eventKind="undeveloped"), leaf("b"))
    issue = only(lint.run(tree, None), "UNDEVELOPED_EVENT")[0]
    assert issue["severity"] == "info" and issue["nodeId"] == "u"


def test_pand_approx():
    tree = top(gate("p", [leaf("x"), leaf("y")], "AND", gateType="PAND"), leaf("b"))
    issue = only(lint.run(tree, None), "PAND_APPROX")[0]
    assert issue["severity"] == "info" and issue["params"] == {"n": 2}


def test_session_warnings_pass_through():
    warnings = [
        {"severity": "warning", "code": "LOAD_REPAIR", "nodeId": "a",
         "message": "Duplicate id renamed.", "params": {"kind": "duplicate_id"}},
        {"severity": "warning", "code": "LINKS_REMOVED", "nodeId": "b",
         "message": "Link removed.", "params": {"nodeId": "b", "targetId": "z"}},
        {"severity": "warning", "code": "LINKS_REMOVED", "nodeId": "b",
         "message": "Another link removed.", "params": {"nodeId": "b", "targetId": "y"}},
    ]
    issues = lint.run(clean(), None, warnings)
    assert codes(issues) == ["LOAD_REPAIR", "LINKS_REMOVED", "LINKS_REMOVED"]
    assert issues[0]["message"] == "Duplicate id renamed."
    assert issues[0]["nodeName"] == "Na"
    assert all(i["severity"] == "warning" for i in issues)


# ---- mode separation, severities, ordering ---------------------------------------------------


def _messy():
    return top(
        leaf("a", 1.0, links=[{"target_id": "ghost", "relation": "OR"}]),
        gate("x", [leaf("p")], gateType="XOR"),
        leaf("u", 0.2, eventKind="undeveloped"),
        gate("g", [leaf("q", 0.5)], "AND", p=0.3),
    )


def test_eta_mode_skips_fta_rules_and_fta_mode_skips_eta_rules():
    tree = _messy()
    fta = set(codes(lint.run(tree, None)))
    assert {"DANGLING_LINK", "XOR_ARITY", "UNDEVELOPED_EVENT", "DEFAULT_PROBABILITY",
            "SINGLE_INPUT_GATE"} <= fta
    assert "ETA_BRANCH_SUM" not in fta
    eta = set(codes(lint.run(tree, None, mode="ETA")))
    assert eta == {"ETA_BRANCH_SUM"}


def test_every_code_has_one_severity_and_the_plan_list_is_complete():
    frozen = {
        "SINGLE_INPUT_GATE", "DEFAULT_PROBABILITY", "UNDEVELOPED_EVENT", "DANGLING_LINK",
        "CYCLIC_LINK", "LOAD_REPAIR", "LINKS_REMOVED", "INHIBIT_ARITY", "KOFN_ARITY",
        "XOR_ARITY", "PAND_APPROX", "TRANSFER_MISSING", "TRANSFER_CYCLE",
        "TRANSFER_HAS_CHILDREN", "HOUSE_HAS_CHILDREN", "ETA_BRANCH_SUM",
        "PARENT_PROBABILITY_IGNORED", "QUANT_PARAM_MISSING", "STANDBY_LARGE_LT",
        "NONCOHERENT_XOR", "CUTSETS_TRUNCATED", "RATE_IMPLAUSIBLE",
    }
    assert set(lint.CODES) == frozen
    assert set(lint.SEVERITY.values()) == set(lint.SEVERITIES)
    assert set(lint.MESSAGES) == frozen


def test_sorted_by_severity_then_tree_order_and_deterministic():
    tree = _messy()
    warnings = [{"severity": "warning", "code": "LOAD_REPAIR", "nodeId": "gone",
                 "message": "m", "params": {}}]
    issues = lint.run(tree, None, warnings)
    ranks = [lint.SEVERITIES.index(i["severity"]) for i in issues]
    assert ranks == sorted(ranks)
    order = ["root", "a", "x", "p", "u", "g", "q"]
    for sev in lint.SEVERITIES:
        positions = [order.index(i["nodeId"]) if i["nodeId"] in order else 99
                     for i in issues if i["severity"] == sev]
        assert positions == sorted(positions), sev
    assert issues[-1 - sum(1 for i in issues if i["severity"] == "info")]["nodeId"] == "gone"
    assert lint.run(tree, None, warnings) == issues


def test_issue_shape():
    for issue in lint.run(_messy(), None):
        assert set(issue) == {"severity", "code", "nodeId", "nodeName", "message", "params",
                              "hintKey"}
        assert issue["hintKey"] == "val.fix." + issue["code"]
        assert "{" not in issue["message"], issue["message"]


#: Codes added on the Python side whose UI strings land from the frontend
#: branch in parallel (1.7.1). Checked like every other code as soon as
#: val.js has them; drop an entry once both branches are merged.
PENDING_I18N = {"RATE_IMPLAUSIBLE"}


def test_every_code_is_localised_with_a_fix_hint():
    src = VAL_JS.read_text(encoding="utf-8")
    en_block, ja_block = src.split("\n  ja:", 1)
    for code in lint.CODES:
        if code in PENDING_I18N and "'val.code.%s'" % code not in src:
            continue
        for block in (en_block, ja_block):
            assert "'val.code.%s'" % code in block, code
            assert "'val.fix.%s'" % code in block, code
    # Every {param} the UI interpolates is one lint actually provides.
    placeholders = dict(re.findall(r"'val\.code\.([A-Z_]+)':\s*'([^']*)'", en_block))
    provided = {
        "DANGLING_LINK": {"targetId"}, "TRANSFER_CYCLE": {"transferTo"},
        "INHIBIT_ARITY": {"n", "conditions"}, "KOFN_ARITY": {"k", "n"}, "XOR_ARITY": {"n"},
        "QUANT_PARAM_MISSING": {"model", "missing"}, "CYCLIC_LINK": {"targetName"},
        "TRANSFER_HAS_CHILDREN": {"n"}, "HOUSE_HAS_CHILDREN": {"n"}, "SINGLE_INPUT_GATE": {"gate"},
        "PARENT_PROBABILITY_IGNORED": {"probability", "calculated"},
        "STANDBY_LARGE_LT": {"lambdaTau"}, "NONCOHERENT_XOR": {"count"},
        "RATE_IMPLAUSIBLE": {"lambda", "unit", "q", "model"},
        "CUTSETS_TRUNCATED": {"reason"}, "ETA_BRANCH_SUM": {"sum"},
        "LINKS_REMOVED": {"targetId"}, "PAND_APPROX": {"n"},
        # 1.7.1 (lint rule added on the backend branch): params {lambda, unit, q, model}
        "RATE_IMPLAUSIBLE": {"lambda", "unit", "q", "model"},
    }
    for code, text in placeholders.items():
        used = set(re.findall(r"\{(\w+)\}", text))
        assert used <= provided.get(code, set()), (code, used)


# ---- performance -----------------------------------------------------------------------------


def _random_tree(n, seed=7):
    rng = random.Random(seed)
    root = top()
    nodes = [root]
    for i in range(n - 1):
        parent = rng.choice(nodes[: max(1, len(nodes))])
        node = leaf("n%d" % i, rng.choice([0.1, 0.01, 1.0]))
        node["logicGate"] = rng.choice(["AND", "OR"])
        parent["children"].append(node)
        nodes.append(node)
    for node in rng.sample(nodes, n // 20):
        target = rng.choice(nodes)
        node["links"].append({"target_id": target["id"], "relation": rng.choice(["AND", "OR"])})
    return root


def test_performance_on_a_thousand_nodes():
    tree = _random_tree(1000)
    lint.run(tree, None)  # warm-up
    start = time.perf_counter()
    issues = lint.run(tree, None)
    elapsed = time.perf_counter() - start
    assert issues
    assert elapsed < 0.5, elapsed
