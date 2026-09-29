"""
Regenerate the back-to-back (B2B) test corpus in this directory.

    uv run --frozen python fta_web/tests/b2b/make_corpus.py

Deterministic: every random tree is built from a fixed seed, so running this
twice writes byte-identical files. The JSON files are committed; this script
documents how they were made and rebuilds them after a deliberate change.

``expected.json`` holds the hand-computed answers for the textbook trees.
They are computed here from closed-form formulas (never through the engine),
so a disagreement with the engine is a real disagreement.

See README.md for what each file covers.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
DATE = "2026-09-28"

_PROJECTION = {"AND": "AND", "INHIBIT": "AND", "PAND": "AND",
               "OR": "OR", "KOFN": "OR", "XOR": "OR", "TRANSFER": "OR"}


# ---- node builders -----------------------------------------------------------------


def leaf(nid: str, p: Any, name: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    node = {"id": nid, "name": name if name is not None else nid, "type": "Event",
            "probability": p, "logicGate": "OR", "notes": "", "links": [], "children": []}
    node.update(extra)
    return node


def gate(nid: str, kind: str, children: List[Dict[str, Any]], name: Optional[str] = None,
         **extra: Any) -> Dict[str, Any]:
    node = {"id": nid, "name": name if name is not None else nid, "type": "Event",
            "probability": 1.0, "logicGate": _PROJECTION[kind], "notes": "", "links": [],
            "children": children}
    if kind not in ("AND", "OR"):
        node["gateType"] = kind
    node.update(extra)
    return node


def root(kind: str, children, name: str = "Top event", **extra) -> Dict[str, Any]:
    node = gate("root", kind, children, name=name, **extra)
    node["type"] = "Root"
    return node


def link(target: str, relation: str = "OR") -> Dict[str, str]:
    return {"target_id": target, "relation": relation}


def doc(tree: Dict[str, Any], title: str, mode: str = "FTA",
        analysis: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"title": title, "date": DATE, "mode": mode, "tree": tree}
    if analysis is not None:
        out["analysis"] = analysis
    return out


def legacy_leaf(nid: str, p: Any, name: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    """A 1.6-style leaf: only the keys the desktop app wrote."""
    node = {"id": nid, "name": name if name is not None else nid, "type": "Event",
            "probability": p, "logicGate": "OR", "children": [], "links": [], "notes": ""}
    node.update(extra)
    return node


def legacy_gate(nid: str, gate_value: str, children, name: Optional[str] = None,
                **extra: Any) -> Dict[str, Any]:
    node = {"id": nid, "name": name if name is not None else nid, "type": "Event",
            "probability": 1.0, "logicGate": gate_value, "children": children,
            "links": [], "notes": ""}
    node.update(extra)
    return node


# ---- the corpus -----------------------------------------------------------------------

FILES: Dict[str, Any] = {}
EXPECTED: Dict[str, Dict[str, Any]] = {}


def add(name: str, document: Any, expected: Optional[Dict[str, Any]] = None,
        minified: bool = False) -> None:
    FILES[name] = (document, minified)
    if expected is not None:
        EXPECTED[name] = expected


def or_(*ps: float) -> float:
    """1 - Π(1 - p), computed without cancellation (the product form loses
    digits for small p -- the very bug the B2B run found in the engine)."""
    if any(p >= 1.0 for p in ps):
        return 1.0
    return -math.expm1(math.fsum(math.log1p(-p) for p in ps))


def and_(*ps: float) -> float:
    out = 1.0
    for p in ps:
        out *= p
    return out


def build_legacy() -> None:
    # L01 -- plain AND/OR, 3 levels, the document format.
    t = legacy_gate("root", "OR", [
        legacy_gate("g1", "AND", [legacy_leaf("a", 0.1), legacy_leaf("b", 0.2)], name="Pumps"),
        legacy_gate("g2", "OR", [legacy_leaf("c", 0.05), legacy_leaf("d", 0.01),
                                 legacy_gate("g3", "AND", [legacy_leaf("e", 0.3),
                                                           legacy_leaf("f", 0.4)])]),
    ], name="System failure", type="Root")
    g3 = and_(0.3, 0.4)
    g2 = or_(0.05, 0.01, g3)
    g1 = and_(0.1, 0.2)
    add("L01_and_or_basic.json", doc(t, "L01 AND/OR basic"),
        {"top": or_(g1, g2), "exact": True, "nodes": {"g1": g1, "g2": g2, "g3": g3},
         "why": "OR(AND(.1,.2), OR(.05,.01,AND(.3,.4))) by hand"})

    # L02 -- the same tree, bare (no metadata wrapper): the oldest legacy format.
    bare = json.loads(json.dumps(t))
    add("L02_bare_tree.json", bare, {"top": or_(g1, g2), "exact": True,
                                     "why": "same numbers as L01"})

    # L03 -- {"FTA": tree}, the other legacy wrapper.
    add("L03_fta_wrapper.json", {"FTA": json.loads(json.dumps(t))},
        {"top": or_(g1, g2), "exact": True, "why": "same numbers as L01"})

    # L04 -- links: AND-link and OR-link to leaves and to a gate (acyclic).
    t = legacy_gate("root", "OR", [
        legacy_gate("g1", "AND", [legacy_leaf("a", 0.1), legacy_leaf("b", 0.2)],
                    links=[{"target_id": "c", "relation": "AND"}]),
        legacy_gate("g2", "OR", [legacy_leaf("c", 0.3), legacy_leaf("d", 0.4)],
                    links=[{"target_id": "g3", "relation": "OR"}]),
        legacy_gate("g3", "AND", [legacy_leaf("e", 0.5), legacy_leaf("f", 0.6)],
                    links=[{"target_id": "a", "relation": "and"}]),
    ], name="Links", type="Root")
    g3 = and_(0.5, 0.6) * 0.1
    g2 = or_(or_(0.3, 0.4), g3)
    g1 = and_(0.1, 0.2) * 0.3
    add("L04_links_and_or.json", doc(t, "L04 links"),
        {"treeWalk": or_(g1, g2, g3), "nodes": {"g1": g1, "g2": g2, "g3": g3},
         "why": "gate first, then AND-links (x), then OR-links (union); repeated a, c"})

    # L05 -- link cycle (D17): G(OR, child .01) <-> B(.02) both ways, plus a
    # leaf that links to itself.
    t = legacy_gate("root", "OR", [
        legacy_gate("G", "OR", [legacy_leaf("x", 0.01)],
                    links=[{"target_id": "B", "relation": "OR"}]),
        legacy_leaf("B", 0.02, links=[{"target_id": "G", "relation": "OR"}]),
        legacy_leaf("S", 0.05, links=[{"target_id": "S", "relation": "OR"}]),
    ], name="Cycle", type="Root")
    add("L05_link_cycle.json", doc(t, "L05 link cycle"))

    # L06 -- a deep chain (depth 120), alternating AND/OR with a side leaf.
    node = legacy_leaf("deep_leaf", 0.5)
    for i in range(119, -1, -1):
        g = "AND" if i % 2 else "OR"
        node = legacy_gate("d%d" % i, g, [node, legacy_leaf("s%d" % i, 0.9 if g == "AND" else 0.01)])
    node["id"] = "root"
    node["type"] = "Root"
    add("L06_deep_chain.json", doc(node, "L06 deep chain"))

    # L07 -- ETA mode.
    t = legacy_gate("root", "", [
        legacy_gate("s1", "", [legacy_leaf("s1a", 0.9), legacy_leaf("s1b", 0.1)], probability=0.999),
        legacy_gate("f1", "", [legacy_leaf("f1a", 0.3), legacy_leaf("f1b", 0.7)], probability=1e-4),
    ], name="Initiator", type="Root", probability=1e-2)
    add("L07_eta_mode.json", doc(t, "L07 ETA", mode="ETA"),
        {"nodes": {"root": 1e-2, "s1": 1e-2 * 0.999, "s1a": 1e-2 * 0.999 * 0.9,
                   "f1": 1e-6, "f1a": 3e-7, "f1b": 7e-7},
         "why": "ETA: child calc = parent calc x child base (desktop: 3e-7 -> 0, D14)"})

    # L08 -- probabilities spanning 1e-12..1 (D14: the desktop app rounds to 6 decimals).
    t = legacy_gate("root", "OR", [
        legacy_gate("tiny_and", "AND", [legacy_leaf("t1", 1e-3), legacy_leaf("t2", 1e-4)]),
        legacy_gate("tiny_or", "OR", [legacy_leaf("t3", 3e-7), legacy_leaf("t4", 4e-7)]),
        legacy_gate("mixed", "AND", [legacy_leaf("m1", 1e-12), legacy_leaf("m2", 0.999999)]),
        legacy_leaf("big", 1e-9),
    ], name="Span", type="Root")
    add("L08_prob_span.json", doc(t, "L08 1e-12..1"),
        {"nodes": {"tiny_and": 1e-7, "tiny_or": or_(3e-7, 4e-7), "mixed": 1e-12 * 0.999999},
         "top": or_(1e-7, or_(3e-7, 4e-7), 1e-12 * 0.999999, 1e-9), "exact": True,
         "why": "D14: 1e-7 must not flush to 0"})

    # L09 -- zeros and ones.
    t = legacy_gate("root", "OR", [
        legacy_gate("and0", "AND", [legacy_leaf("z", 0.0), legacy_leaf("h", 0.5)]),
        legacy_gate("or1", "OR", [legacy_leaf("one", 1.0), legacy_leaf("q", 0.25)]),
        legacy_gate("and1", "AND", [legacy_leaf("one2", 1), legacy_leaf("q2", "0.25")]),
    ], name="Zero/one", type="Root")
    add("L09_zero_one.json", doc(t, "L09 zero/one"),
        {"nodes": {"and0": 0.0, "or1": 1.0, "and1": 0.25}, "top": 1.0, "exact": True,
         "why": "AND with 0 is 0, OR with 1 is 1; '0.25' string and int 1 accepted"})

    # L10 -- duplicate ids (D15).
    t = legacy_gate("root", "OR", [legacy_leaf("e1", 0.1), legacy_leaf("e1", 0.9),
                                   legacy_gate("g", "AND", [legacy_leaf("e2", 0.5),
                                                            legacy_leaf("e2", 0.5)])],
                    name="Dups", type="Root")
    add("L10_duplicate_ids.json", doc(t, "L10 duplicate ids"),
        {"top": or_(0.1, 0.9, 0.25), "exact": True,
         "why": "D15: second e1 is renamed e1_dup2 and keeps its own 0.9 (desktop: 0.19)"})

    # L11 -- Unicode and markup characters in names.
    t = legacy_gate("root", "OR", [
        legacy_leaf("u1", 0.01, name="ポンプ故障 <P-101> & \"motor\""),
        legacy_leaf("u2", 0.02, name="Ventil ü/ß – ‘quote’ '<b>'"),
        legacy_gate("u3", "AND", [legacy_leaf("u4", 0.5, name="冷却水 > 限界"),
                                  legacy_leaf("u5", 0.5, name="a&b<c>d")], name="系統 A&B"),
    ], name="トップ事象 <Top> & more", type="Root")
    add("L11_unicode_names.json", doc(t, "L11 Unicode ユニコード <&>"),
        {"top": or_(0.01, 0.02, 0.25), "exact": True, "why": "names never change numbers"})

    # L12 -- top id is not "root" (D16), with a link to the old top id.
    t = legacy_gate("TOP", "AND", [
        legacy_leaf("a", 0.5),
        legacy_gate("g", "OR", [legacy_leaf("b", 0.2)], links=[{"target_id": "a", "relation": "OR"}]),
    ], name="Top with id TOP", type="Root")
    add("L12_top_not_root.json", doc(t, "L12 top id TOP"),
        {"treeWalk": 0.5 * or_(0.2, 0.5), "why": "AND(a, OR(b)+OR-link a): a repeated"})

    # L13 -- a minified document (D8: the desktop loader mangles it).
    t = legacy_gate("root", "AND", [legacy_leaf("a", 0.1), legacy_leaf("b", 0.2)],
                    name="Minified", type="Root")
    add("L13_minified.json", doc(t, "L13 minified"), {"top": 0.02, "exact": True},
        minified=True)

    # L14 -- gate spellings the loader normalises: lower case, empty, None,
    # missing, and an unknown gate ("NOT" computes as OR); string probability.
    t = {"id": "root", "name": "Spellings", "type": "Root", "logicGate": "or",
         "probability": 1.0, "children": [
             {"id": "lc_and", "name": "lower-case and", "logicGate": "and", "children": [
                 {"id": "p1", "name": "p1", "probability": "0.5"},
                 {"id": "p2", "name": "p2", "probability": 0.5},
                 {"id": "p7", "name": "p7 (no probability: 1.0)"}]},
             {"id": "empty", "name": "empty gate", "logicGate": "", "children": [
                 {"id": "p3", "name": "p3", "probability": 0.1},
                 {"id": "p4", "name": "p4", "probability": 0.1}]},
             {"id": "none_gate", "name": "None gate", "logicGate": None, "children": [
                 {"id": "p5", "name": "p5", "probability": 0.1}]},
             {"id": "missing", "name": "missing gate", "children": [
                 {"id": "p6", "name": "p6", "probability": 0.2},
                 {"id": "p6b", "name": "p6b", "probability": 0.1}]},
             {"id": "not_gate", "name": "NOT gate", "logicGate": "NOT", "children": [
                 {"id": "p8", "name": "p8", "probability": 0.3}]},
         ]}
    lc = 0.25
    em = or_(0.1, 0.1)
    ng = 0.1
    mi = or_(0.2, 0.1)
    nt = 0.3
    add("L14_gate_spellings.json", doc(t, "L14 gate spellings"),
        {"nodes": {"lc_and": lc, "empty": em, "none_gate": ng, "missing": mi, "not_gate": nt},
         "top": or_(lc, em, ng, mi, nt), "exact": True,
         "why": "and->AND, ''/None/missing->OR, NOT->OR, missing probability->1.0"})

    # L15 -- dangling and malformed links.
    t = legacy_gate("root", "OR", [
        legacy_gate("g", "AND", [legacy_leaf("a", 0.5), legacy_leaf("b", 0.5)],
                    links=[{"target_id": "nowhere", "relation": "AND"},
                           {"target_id": "", "relation": "OR"},
                           {"relation": "OR"},
                           {"target_id": "c", "relation": None}]),
        legacy_leaf("c", 0.1),
    ], name="Dangling", type="Root")
    g = or_(0.25, 0.1)
    add("L15_dangling_links.json", doc(t, "L15 dangling links"),
        {"nodes": {"g": g}, "treeWalk": or_(g, 0.1),
         "why": "a missing / empty target is skipped; relation None -> OR"})


    # L16 -- tiny OR inputs: the 1.6 product form 1 - Π(1 - p) cancelled
    # them (OR(1e-17, 1e-17) = 0). Found by this B2B run; fixed in 1.7.1.
    t = legacy_gate("root", "OR", [
        legacy_gate("t1", "OR", [legacy_leaf("x1", 1e-17), legacy_leaf("x2", 1e-17)]),
        legacy_gate("t2", "AND", [legacy_leaf("y%d" % i, 1e-6) for i in range(3)]),
        legacy_gate("t3", "AND", [legacy_leaf("z%d" % i, 1e-6) for i in range(3)]),
        legacy_gate("t4", "OR", [legacy_leaf("w1", 1e-15)],
                    links=[{"target_id": "w2", "relation": "OR"}]),
        legacy_leaf("w2", 3e-15),
    ], name="Tiny OR", type="Root")
    t4 = or_(1e-15, 3e-15)
    add("L16_tiny_or.json", doc(t, "L16 tiny OR inputs"),
        {"nodes": {"t1": 2e-17, "t2": 1e-18, "t3": 1e-18, "t4": t4},
         "treeWalk": or_(2e-17, 1e-18, 1e-18, t4, 3e-15),
         "why": "OR of tiny values keeps every digit (1.6 gave t1 = 0)"})


def build_features() -> None:
    # F01 -- every quant model; λ in FIT (stored per hour); T default vs override;
    # repairable by mu and by mttr (mu wins when both); standby λτ > 0.2.
    mission = 4380.0
    fit = 250 * 1e-9
    t = root("OR", [
        leaf("fixed", 0.01, quant={"model": "fixed"}),
        leaf("rate_T", 0.5, quant={"model": "rate", "lambda": 1e-5, "T": 1000.0}),
        leaf("rate_mission", 0.5, quant={"model": "rate", "lambda": 2e-6}),
        leaf("rate_fit", 0.5, name="rate 250 FIT", quant={"model": "rate", "lambda": fit}),
        leaf("standby", 0.5, quant={"model": "standby", "lambda": 1e-4, "tau": 720.0}),
        leaf("standby_big", 0.5, quant={"model": "standby", "lambda": 1e-3, "tau": 500.0}),
        leaf("rep_mttr", 0.5, quant={"model": "repairable", "lambda": 1e-3, "mttr": 10.0}),
        leaf("rep_mu", 0.5, quant={"model": "repairable", "lambda": 1e-3, "mu": 0.05,
                                   "mttr": 10.0}),
    ])
    q = {
        "fixed": 0.01,
        "rate_T": -math.expm1(-1e-5 * 1000.0),
        "rate_mission": -math.expm1(-2e-6 * mission),
        "rate_fit": -math.expm1(-fit * mission),
        "standby": 1e-4 * 720.0 / 2.0,
        "standby_big": min(1.0, 1e-3 * 500.0 / 2.0),
        "rep_mttr": 1e-3 / (1e-3 + 0.1),
        "rep_mu": 1e-3 / (1e-3 + 0.05),
    }
    add("F01_quant_models.json", doc(t, "F01 quant models", analysis={"missionTime": mission}),
        {"q": q, "top": or_(*q.values()), "exact": True,
         "why": "rate 1-exp(-λT) (T defaults to missionTime 4380 h), standby λτ/2, "
                "repairable λ/(λ+μ), μ=1/MTTR unless μ given"})

    # F02 -- no analysis block: rate events use the default 8760 h.
    t = root("AND", [leaf("r1", 1.0, quant={"model": "rate", "lambda": 1e-4}),
                     leaf("r2", 1.0, quant={"model": "rate", "lambda": 5e-5})])
    q1 = -math.expm1(-1e-4 * 8760.0)
    q2 = -math.expm1(-5e-5 * 8760.0)
    add("F02_mission_default.json", doc(t, "F02 default mission time"),
        {"q": {"r1": q1, "r2": q2}, "top": q1 * q2, "exact": True,
         "why": "default missionTime = 8760 h"})

    # F03 -- k-out-of-n: 2oo3 of equal p, 1oo2 (= OR), 3oo3 (= AND), 2oo4 unequal.
    p = 0.1
    t = root("OR", [
        gate("v2oo3", "KOFN", [leaf("a1", p), leaf("a2", p), leaf("a3", p)], k=2),
        gate("v1oo2", "KOFN", [leaf("b1", 0.2), leaf("b2", 0.3)], k=1),
        gate("v3oo3", "KOFN", [leaf("c1", 0.5), leaf("c2", 0.4), leaf("c3", 0.3)], k=3),
        gate("v2oo4", "KOFN", [leaf("d1", 0.01), leaf("d2", 0.02), leaf("d3", 0.03),
                               leaf("d4", 0.04)], k=2.0),
    ])
    d = [0.01, 0.02, 0.03, 0.04]
    none = and_(*[1 - x for x in d])
    one = sum(d[i] * and_(*[1 - d[j] for j in range(4) if j != i]) for i in range(4))
    v2oo4 = 1.0 - none - one
    nodes = {"v2oo3": 3 * p * p - 2 * p ** 3, "v1oo2": or_(0.2, 0.3),
             "v3oo3": 0.5 * 0.4 * 0.3, "v2oo4": v2oo4}
    add("F03_kofn.json", doc(t, "F03 k-out-of-n"),
        {"nodes": nodes, "top": or_(*nodes.values()), "exact": True,
         "why": "2oo3 equal p: 3p^2-2p^3; 1oo2 = OR; 3oo3 = AND; 2oo4 = 1-P(0)-P(1)"})

    # F04 -- XOR: two inputs a+b-2ab; three inputs = odd parity (flagged).
    t = root("OR", [
        gate("x2", "XOR", [leaf("a", 0.1), leaf("b", 0.2)]),
        gate("x3", "XOR", [leaf("c", 0.1), leaf("d", 0.2), leaf("e", 0.3)]),
    ])
    x2 = 0.1 + 0.2 - 2 * 0.1 * 0.2
    x3 = (0.1 * 0.8 * 0.7 + 0.9 * 0.2 * 0.7 + 0.9 * 0.8 * 0.3 + 0.1 * 0.2 * 0.3)
    add("F04_xor.json", doc(t, "F04 XOR"),
        {"nodes": {"x2": x2, "x3": x3}, "treeWalk": or_(x2, x3), "exact": True,
         "headlineMethod": "mcub",
         "why": "XOR a+b-2ab; 3-input parity = P(exactly 1)+P(exactly 3)"})

    # F05 -- INHIBIT: input x conditioning; a malformed one (3 children) is still AND.
    t = root("OR", [
        gate("inh", "INHIBIT", [leaf("inp", 0.01), leaf("cond", 0.5, eventKind="conditioning")]),
        gate("inh_bad", "INHIBIT", [leaf("i1", 0.1), leaf("i2", 0.2), leaf("i3", 0.3)]),
    ])
    add("F05_inhibit.json", doc(t, "F05 INHIBIT"),
        {"nodes": {"inh": 0.005, "inh_bad": 0.006}, "top": or_(0.005, 0.006), "exact": True,
         "why": "INHIBIT = input x condition (0.01 x 0.5)"})

    # F06 -- PAND: Πp/n!.
    t = root("OR", [
        gate("pand2", "PAND", [leaf("a", 0.1), leaf("b", 0.2)]),
        gate("pand3", "PAND", [leaf("c", 0.1), leaf("d", 0.2), leaf("e", 0.3)]),
    ])
    add("F06_pand.json", doc(t, "F06 PAND"),
        {"nodes": {"pand2": 0.01, "pand3": 0.001}, "treeWalk": or_(0.01, 0.001),
         "why": "PAND = product / n!; cut sets treat it as AND"})

    # F07 -- TRANSFER: to a gate, missing target, with (ignored) children, a cycle.
    t = root("OR", [
        gate("sub", "AND", [leaf("a", 0.1), leaf("b", 0.2)], name="Subsystem"),
        gate("xfer", "TRANSFER", [], transferTo="sub", name="Transfer to Subsystem"),
        gate("xfer_missing", "TRANSFER", [], transferTo="no_such_node"),
        gate("xfer_kids", "TRANSFER", [leaf("ignored", 0.9)], transferTo="c"),
        leaf("c", 0.05),
        gate("loop1", "TRANSFER", [], transferTo="loop2"),
        gate("loop2", "TRANSFER", [], transferTo="loop1"),
    ])
    add("F07_transfer.json", doc(t, "F07 TRANSFER"),
        {"nodes": {"xfer": 0.02, "xfer_missing": 0.0, "xfer_kids": 0.05, "loop1": 0.0,
                   "loop2": 0.0},
         "why": "transfer = target value; missing/cycle = 0; its children are ignored"})

    # F08 -- house events ON/OFF.
    t = root("OR", [
        gate("h_and_on", "AND", [leaf("hon", 0.3, eventKind="house", houseState=True),
                                 leaf("a", 0.1)]),
        gate("h_and_off", "AND", [leaf("hoff", 0.3, eventKind="house", houseState=False),
                                  leaf("b", 0.2)]),
        gate("h_or_off", "OR", [leaf("hoff2", 0.7, eventKind="house", houseState=False),
                                leaf("c", 0.05)]),
        gate("h_kids", "OR", [leaf("k1", 0.01)], eventKind="house", houseState=True),
    ])
    add("F08_house.json", doc(t, "F08 house events"),
        {"nodes": {"h_and_on": 0.1, "h_and_off": 0.0, "h_or_off": 0.05, "h_kids": 0.01,
                   "hon": 1.0, "hoff": 0.0},
         "top": or_(0.1, 0.0, 0.05, 0.01), "exact": True,
         "why": "house ON = 1, OFF = 0; a house with children is an ordinary gate"})

    # F09 -- undeveloped and conditioning leaves are ordinary basic events numerically.
    t = root("OR", [leaf("u1", 0.01, eventKind="undeveloped"),
                    leaf("u2", 0.02, eventKind="undeveloped"),
                    leaf("b1", 0.03, eventKind="basic")])
    add("F09_undeveloped.json", doc(t, "F09 undeveloped"),
        {"top": or_(0.01, 0.02, 0.03), "exact": True, "why": "undeveloped = basic"})

    # F10 -- repeated events via links: A AND (A OR B) (the user guide example).
    t = root("AND", [leaf("A", 0.1), gate("G", "OR", [leaf("B", 0.2)], links=[link("A")])])
    add("F10_repeated_links.json", doc(t, "F10 repeated via link"),
        {"exact_top": 0.1, "treeWalk": 0.1 * or_(0.2, 0.1), "mcub": 0.1, "rareEvent": 0.1,
         "cutsets": [["A"]], "headlineMethod": "mcub",
         "why": "A AND (A OR B) = A; tree walk double counts: pA*(pA+pB-pApB)"})

    # F11 -- repeated events via a transfer: OR(AND(A,B), AND(C, TRANSFER->A)).
    t = root("OR", [gate("G1", "AND", [leaf("A", 0.1), leaf("B", 0.2)]),
                    gate("G2", "AND", [leaf("C", 0.3), gate("TA", "TRANSFER", [], transferTo="A")])])
    add("F11_repeated_transfer.json", doc(t, "F11 repeated via transfer"),
        {"exact_top": 0.1 * or_(0.2, 0.3), "treeWalk": or_(0.02, 0.03), "mcub": or_(0.02, 0.03),
         "rareEvent": 0.05, "cutsets": [["A", "B"], ["A", "C"]], "headlineMethod": "mcub",
         "why": "OR(AND(A,B),AND(A,C)) -> cut sets {A,B},{A,C}; exact pA(pB+pC-pBpC)"})

    # F12 -- lognormal uncertainty, analytical means: OR(A,B) series, AND(C,D) parallel.
    ef = 3.0
    sigma = math.log(ef) / 1.645
    t = root("OR", [
        gate("series", "OR", [
            leaf("A", 1e-3, quant={"model": "fixed", "unc": {"dist": "lognormal", "ef": ef}}),
            leaf("B", 5e-4, quant={"model": "fixed", "unc": {"dist": "lognormal", "ef": ef,
                                                               "mean": 2e-3}}),
        ]),
        gate("parallel", "AND", [
            leaf("C", 1e-2, quant={"model": "fixed", "unc": {"dist": "lognormal", "ef": 2.0,
                                                               "median": 1e-2}}),
            leaf("D", 2e-2, quant={"model": "fixed", "unc": {"dist": "lognormal", "ef": 5.0}}),
        ]),
        leaf("R", 0.5, quant={"model": "rate", "lambda": 1e-7, "T": 100.0,
                              "unc": {"dist": "lognormal", "ef": 10.0}}),
    ])
    ea = 1e-3 * math.exp(sigma ** 2 / 2)
    eb = 2e-3  # a mean was entered: E[q] is the mean itself
    s2, s5 = math.log(2.0) / 1.645, math.log(5.0) / 1.645
    ec = 1e-2 * math.exp(s2 ** 2 / 2)
    ed = 2e-2 * math.exp(s5 ** 2 / 2)
    add("F12_uncertainty.json",
        doc(t, "F12 uncertainty", analysis={"mc": {"n": 20000, "seed": 12345}}),
        {"mc_means": {"A": ea, "B": eb, "C": ec, "D": ed,
                      "series": ea + eb - ea * eb, "parallel": ec * ed},
         "why": "lognormal mean = median*exp(σ²/2), σ = ln(EF)/1.645; OR/AND of "
                "independent events: E[a+b-ab] = Ea+Eb-EaEb, E[cd] = EcEd"})

    # F13 -- trace and FMEA blocks (Excel/report columns), RPN computed.
    t = root("OR", [
        leaf("t1", 0.01, trace={"requirementId": "SR-12", "testRef": "TP-3", "owner": "tanaka",
                                "status": "reviewed", "evidence": "https://example.com/e",
                                "tags": ["hydraulic", "hot section"]},
             fmea={"id": "P-07", "item": "Pump", "mode": "Seal leak", "cause": "Wear",
                   "severity": 7, "occurrence": 4, "detection": 3}),
        leaf("t2", 0.02, quant={"model": "rate", "lambda": 1e-6, "source": "OREDA 2015 p.123"},
             fmea={"id": "P-08", "item": "Valve", "mode": "Stuck", "severity": 5,
                   "occurrence": 2, "detection": 2, "rpn": 21}),
    ], trace={"requirementId": "HZ-1", "status": "draft"})
    q2 = -math.expm1(-1e-6 * 8760.0)
    add("F13_trace_fmea.json", doc(t, "F13 trace/FMEA"),
        {"q": {"t1": 0.01, "t2": q2}, "top": or_(0.01, q2), "exact": True,
         "rpn": {"t1": 84, "t2": 21}, "why": "RPN = S*O*D unless given"})

    # F14 -- a realistic mixed plant: every gate and model, links, transfers, house.
    t = root("OR", [
        gate("loss_cooling", "AND", [
            gate("pumps", "KOFN", [
                leaf("P1", 1.0, quant={"model": "repairable", "lambda": 2e-5, "mttr": 24.0,
                                       "unc": {"dist": "lognormal", "ef": 3.0}}),
                leaf("P2", 1.0, quant={"model": "repairable", "lambda": 2e-5, "mttr": 24.0,
                                       "unc": {"dist": "lognormal", "ef": 3.0}}),
                leaf("P3", 1.0, quant={"model": "standby", "lambda": 1e-5, "tau": 730.0}),
            ], k=2, name="2oo3 pumps"),
            gate("power", "OR", [leaf("grid", 1e-2), gate("diesel", "INHIBIT", [
                leaf("dg_fail", 5e-2, quant={"model": "fixed",
                                             "unc": {"dist": "lognormal", "ef": 5.0}}),
                leaf("dg_demand", 0.3, eventKind="conditioning")])]),
        ], name="Loss of cooling"),
        gate("valve_seq", "PAND", [leaf("V1", 1e-3), leaf("V2", 2e-3)], name="Valves in order"),
        gate("sensors", "XOR", [leaf("S1", 1e-3, quant={"model": "rate", "lambda": 1e-7}),
                                leaf("S2", 2e-3)]),
        gate("maint", "AND", [leaf("in_maint", 0.0, eventKind="house", houseState=True),
                              gate("to_power", "TRANSFER", [], transferTo="power")],
             links=[link("V1", "AND")]),
        leaf("operator", 1e-3, eventKind="undeveloped", links=[link("grid", "OR")]),
    ], name="Plant damage")
    add("F14_mixed_plant.json",
        doc(t, "F14 mixed plant", analysis={"missionTime": 720.0, "mc": {"n": 5000, "seed": 7}}))

    # F15 -- a stale gateType (the desktop app switched a KOFN to AND): logicGate wins.
    t = root("OR", [gate("stale", "KOFN", [leaf("a", 0.1), leaf("b", 0.2)], k=2),
                    leaf("c", 0.05)])
    t["children"][0]["logicGate"] = "AND"
    add("F15_stale_gate_type.json", doc(t, "F15 stale gateType"),
        {"nodes": {"stale": 0.02}, "top": or_(0.02, 0.05), "exact": True,
         "why": "gateType KOFN no longer projects to logicGate AND: dropped, AND used"})

    # F16 -- an analysis block with truncating limits and one invalid setting.
    t = root("OR", [gate("g%d" % i, "AND", [leaf("x%d" % i, 0.1 * (i + 1)),
                                            leaf("y%d" % i, 0.05),
                                            leaf("z%d" % i, 0.02 * (i + 1))])
                    for i in range(3)] + [leaf("single", 1e-11)])
    add("F16_analysis_limits.json",
        doc(t, "F16 analysis limits", analysis={
            "missionTime": 100.0, "timeUnit": "d",
            "cutsets": {"maxOrder": 2, "maxCount": 50, "cutoff": 1e-10},
            "mc": {"n": 1000, "seed": 99},
            "fmeaOccurrenceTable": {"5": 1e-3},
            "bogus": 1}))

    # F17 -- missing model parameters keep the previous probability.
    t = root("OR", [leaf("no_lambda", 0.02, quant={"model": "rate", "T": 100.0}),
                    leaf("no_tau", 0.03, quant={"model": "standby", "lambda": 1e-4}),
                    leaf("no_mu", 0.04, quant={"model": "repairable", "lambda": 1e-4})])
    add("F17_quant_missing.json", doc(t, "F17 missing params"),
        {"q": {"no_lambda": 0.02, "no_tau": 0.03, "no_mu": 0.04},
         "top": or_(0.02, 0.03, 0.04), "exact": True,
         "why": "QUANT_PARAM_MISSING: previous probability kept"})


def build_textbook() -> None:
    p = 0.1
    # T01 -- 2oo3 of equal p as a voting gate.
    t = root("KOFN", [leaf("A", p), leaf("B", p), leaf("C", p)], k=2)
    add("T01_2oo3.json", doc(t, "T01 2oo3 voting"),
        {"top": 3 * p ** 2 - 2 * p ** 3, "exact": True, "exact_top": 0.028,
         "mcub": or_(p * p, p * p, p * p), "rareEvent": 3 * p * p,
         "cutsets": [["A", "B"], ["A", "C"], ["B", "C"]],
         "why": "2oo3 equal p: 3p^2-2p^3 = 0.028"})

    # T02 -- 2oo3 built from AND/OR with repeated events (links): same exact value.
    t = root("OR", [gate("AB", "AND", [leaf("A", p), leaf("B", p)]),
                    gate("AC", "AND", [leaf("C", p)], links=[link("A", "AND")]),
                    gate("BC", "AND", [gate("TB", "TRANSFER", [], transferTo="B"),
                                       gate("TC", "TRANSFER", [], transferTo="C")])])
    add("T02_2oo3_expanded.json", doc(t, "T02 2oo3 expanded (repeated events)"),
        {"exact_top": 0.028, "treeWalk": or_(p * p, p * p, p * p),
         "mcub": or_(p * p, p * p, p * p), "rareEvent": 3 * p * p,
         "cutsets": [["A", "B"], ["A", "C"], ["B", "C"]], "headlineMethod": "mcub",
         "why": "OR(AB, AC+link A, AND(xfer B, xfer C)): exact 0.028, MCUB 1-(1-p^2)^3"})

    # T03 -- standby λτ/2 and exponential rate model, by hand.
    t = root("OR", [leaf("SB", 1.0, quant={"model": "standby", "lambda": 1e-4, "tau": 720.0}),
                    leaf("EXP", 1.0, quant={"model": "rate", "lambda": 1e-5, "T": 1000.0})])
    sb = 1e-4 * 720 / 2
    ex = 1 - math.exp(-0.01)
    add("T03_standby_exp.json", doc(t, "T03 standby + exponential"),
        {"q": {"SB": sb, "EXP": ex}, "top": or_(sb, ex), "exact": True,
         "why": "standby λτ/2 = 0.036; rate 1-exp(-λT) = 1-e^-0.01"})

    # T04 -- series-parallel: AND(OR(A,B), OR(C,D)).
    t = root("AND", [gate("L", "OR", [leaf("A", 0.1), leaf("B", 0.2)]),
                     gate("R", "OR", [leaf("C", 0.3), leaf("D", 0.4)])])
    add("T04_series_parallel.json", doc(t, "T04 series-parallel"),
        {"top": or_(0.1, 0.2) * or_(0.3, 0.4), "exact": True, "exact_top": 0.28 * 0.58,
         "cutsets": [["A", "C"], ["A", "D"], ["B", "C"], ["B", "D"]],
         "mcub": or_(0.03, 0.04, 0.06, 0.08), "rareEvent": 0.21,
         "why": "(1-0.9*0.8)(1-0.7*0.6) = 0.28*0.58 = 0.1624"})

    # T05 -- repairable steady state.
    t = root("AND", [leaf("R1", 1.0, quant={"model": "repairable", "lambda": 1e-3, "mttr": 10.0}),
                     leaf("R2", 1.0, quant={"model": "repairable", "lambda": 1e-3, "mu": 0.1})])
    r = 1e-3 / (1e-3 + 0.1)
    add("T05_repairable.json", doc(t, "T05 repairable"),
        {"q": {"R1": r, "R2": r}, "top": r * r, "exact": True,
         "why": "λ/(λ+μ) with μ = 1/MTTR = 0.1"})

    # T06 -- single point of failure: OR(A, AND(B,C)) importance by hand.
    t = root("OR", [leaf("A", 0.01), gate("BC", "AND", [leaf("B", 0.1), leaf("C", 0.2)])])
    qa, qbc = 0.01, 0.02
    top = or_(qa, qbc)
    add("T06_importance.json", doc(t, "T06 importance by hand"),
        {"top": top, "exact": True, "mcub": top, "cutsets": [["A"], ["B", "C"]],
         "importance": {
             "A": {"birnbaum": 1 - qbc, "fv": (top - qbc) / top, "raw": 1 / top,
                   "rrw": top / qbc},
             "B": {"birnbaum": 0.2 * (1 - qa), "fv": (top - qa) / top,
                   "raw": or_(qa, 0.2) / top, "rrw": top / qa},
         },
         "why": "Q = 1-(1-qa)(1-qb qc); Birnbaum_A = 1-qbqc; Birnbaum_B = qc(1-qa)"})


def _random_tree(rng: random.Random, n_events: int, prefix: str, legacy: bool,
                 p_and: float, links: int, kofn: float = 0.0, quant: float = 0.0,
                 cycles: bool = False, hot: bool = False) -> Dict[str, Any]:
    """Bottom-up random tree: n leaves grouped 2..4 at a time under new gates.

    ``hot`` draws large probabilities (0.01..0.3) so the small oracle trees
    have top values and cut sets well above the default cutoff."""
    make_leaf = legacy_leaf if legacy else leaf
    pool: List[Dict[str, Any]] = []
    leaves: List[Dict[str, Any]] = []
    for i in range(n_events):
        p = 10 ** (rng.uniform(-2, -0.5) if hot else rng.uniform(-6, -1.3))
        node = make_leaf("%se%d" % (prefix, i), float("%.4g" % p), name="Event %d" % i)
        if quant and rng.random() < quant:
            model = rng.choice(["rate", "standby", "repairable"])
            if model == "rate":
                lo, hi = (-6, -4.5) if hot else (-8, -5)
                node["quant"] = {"model": "rate", "lambda": float("%.3g" % (10 ** rng.uniform(lo, hi)))}
            elif model == "standby":
                lo, hi = (-5, -3.5) if hot else (-7, -5)
                node["quant"] = {"model": "standby", "lambda": float("%.3g" % (10 ** rng.uniform(lo, hi))),
                                 "tau": rng.choice([168.0, 730.0, 2190.0])}
            else:
                lo, hi = (-4, -3) if hot else (-6, -4)
                node["quant"] = {"model": "repairable", "lambda": float("%.3g" % (10 ** rng.uniform(lo, hi))),
                                 "mttr": rng.choice([8.0, 24.0, 72.0])}
            if rng.random() < 0.5:
                node["quant"]["unc"] = {"dist": "lognormal", "ef": rng.choice([3.0, 5.0, 10.0])}
        pool.append(node)
        leaves.append(node)
    gates: List[Dict[str, Any]] = []
    counter = 0
    while len(pool) > 1:
        size = min(len(pool), rng.choice([2, 2, 3, 3, 4]))
        picks = [pool.pop(rng.randrange(len(pool))) for _ in range(size)]
        r = rng.random()
        if not legacy and kofn and r < kofn and size >= 3:
            g = gate("%sg%d" % (prefix, counter), "KOFN", picks, k=rng.randint(2, size - 1))
        elif r < kofn + p_and and size <= 3:
            g = (legacy_gate if legacy else gate)("%sg%d" % (prefix, counter), "AND", picks)
        else:
            g = (legacy_gate if legacy else gate)("%sg%d" % (prefix, counter), "OR", picks)
        counter += 1
        gates.append(g)
        pool.append(g)
    top = pool[0]
    top["id"] = "root"
    top["type"] = "Root"
    top["name"] = "Random top"
    # Repeated events: gate -> leaf links never close a loop (leaves have none).
    for _ in range(links):
        g = rng.choice(gates)
        target = rng.choice(leaves)
        g.setdefault("links", []).append(
            {"target_id": target["id"], "relation": "AND" if rng.random() < 0.3 else "OR"})
    if cycles:
        # A few gate -> gate links in both directions (only the legacy
        # comparison uses these: they exercise D17).
        for _ in range(3):
            a, b = rng.sample(gates, 2)
            a.setdefault("links", []).append({"target_id": b["id"], "relation": "OR"})
            b.setdefault("links", []).append({"target_id": a["id"], "relation": "OR"})
    return top


def build_random() -> None:
    # Small coherent random trees for the truth-table oracle (<= 14 events).
    for k, (n, p_and, links, kofn) in enumerate(
            [(8, 0.4, 0, 0.0), (10, 0.35, 2, 0.0), (12, 0.3, 3, 0.2), (14, 0.35, 4, 0.15),
             (11, 0.5, 5, 0.0), (13, 0.3, 2, 0.3)], start=1):
        rng = random.Random(1000 + k)
        t = _random_tree(rng, n, "o%d_" % k, legacy=False, p_and=p_and, links=links, kofn=kofn,
                         quant=0.3, hot=True)
        add("O%02d_random_oracle.json" % k, doc(t, "O%02d random (oracle)" % k))

    # A random legacy tree (links incl. cycles) for the desktop comparison.
    rng = random.Random(4242)
    t = _random_tree(rng, 400, "lg_", legacy=True, p_and=0.3, links=25, cycles=True)
    add("R00_random_legacy_400.json", doc(t, "R00 random legacy 400"))

    # Large random 1.7 trees (performance / consistency).
    for name, n, seed, p_and in (("R01_random_300.json", 300, 301, 0.22),
                                 ("R02_random_800.json", 800, 802, 0.22),
                                 ("R03_random_2000.json", 2000, 2003, 0.12)):
        rng = random.Random(seed)
        t = _random_tree(rng, n, "r_", legacy=False, p_and=p_and, links=n // 60, kofn=0.04,
                         quant=0.3)
        add(name, doc(t, name[:-5], analysis={"mc": {"n": 2000, "seed": seed}}))


def main() -> None:
    build_legacy()
    build_features()
    build_textbook()
    build_random()
    for name, (document, minified) in FILES.items():
        path = HERE / name
        if minified:
            text = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
        else:
            # indent=0 (newlines, no indentation) keeps the deep and the large files
            # small without minifying them (the desktop loader mangles minified
            # documents, D8 -- only L13 is meant to test that).
            big = name.startswith(("R", "L06"))
            text = json.dumps(document, ensure_ascii=False, indent=0 if big else 2)
        path.write_text(text + ("" if minified else "\n"), encoding="utf-8", newline="\n")
    (HERE / "expected.json").write_text(
        json.dumps(EXPECTED, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    print("wrote %d corpus files + expected.json to %s" % (len(FILES), HERE))


if __name__ == "__main__":
    main()
