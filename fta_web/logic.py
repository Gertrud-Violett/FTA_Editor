"""
The structure function of a fault tree (workstream A).

:func:`compile_tree` turns the document tree into a small formula graph -- a
DAG of Boolean operators over *events* -- that the cut-set, importance and
Monte Carlo modules share. The graph mirrors ``engine.WebCore``'s tree walk
**operation for operation**: the same traversal order, the same identity memo,
the same cycle fallback, AND-links then OR-links. Evaluating the graph with
the engine's gate formulas therefore reproduces the tree walk exactly, and
reading it as Boolean logic gives the cut sets of the *same* model.

Variables
---------
Every leaf (``basic``, ``undeveloped`` or ``conditioning``) is a variable keyed
by its node **id**, so an event reached along several paths (links, transfers)
is one variable -- a *repeated event*. A ``house`` leaf is the constant
``houseState``. A TRANSFER node is the formula of its ``transferTo`` target.

Gate semantics (as in the engine)
---------------------------------
``F(node) = OR( AND( G(children), AND-link targets... ), OR-link targets... )``
with G from ``gateType`` (falling back to ``logicGate``):

* AND / OR -- as named; INHIBIT is AND; PAND is AND (and listed as an
  approximation: the engine's Πp/n! has no Boolean counterpart).
* KOFN -- at least k of n (``k`` invalid -> 1, as the engine does).
* XOR -- kept as its own operator for numeric evaluation; Boolean readers
  treat it as OR and the result is flagged ``nonCoherent``.
* A link to a node still on the walk's stack uses that node's gate-only
  formula when the engine would (``CYCLIC_LINK`` otherwise, and the link is
  skipped). A transfer that loops is FALSE (``TRANSFER_CYCLE``); a missing or
  self transfer is FALSE (``TRANSFER_MISSING``).

Graph encoding
--------------
``Structure.ops`` is a list; an operator's children always have smaller
indices (post-order), so index order is a topological order. Each op is a
tuple whose first item is the kind:

``("const", bool)``, ``("var", event_index)``, ``("and", refs)``,
``("or", refs)``, ``("kofn", k, refs)``, ``("xor", refs)``, ``("pand", refs)``

``Structure.op_nodes[i]`` is the tree node id op ``i`` came from (None for
variables/constants shared across nodes).
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Optional, Tuple

try:  # normal package import: ``import fta_web.logic``
    from . import engine
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import engine  # type: ignore[no-redef]

_GATE_KINDS = ("AND", "OR", "KOFN", "XOR", "INHIBIT", "PAND")

#: Engine warning codes that describe a modelling approximation.
APPROX_CODES = ("PAND_APPROX", "XOR_ARITY", "STANDBY_LARGE_LT")


class Structure:
    """The compiled formula graph plus what the readers need to know."""

    def __init__(self) -> None:
        self.ops: List[tuple] = []
        self.op_nodes: List[Optional[str]] = []
        self.top: Optional[int] = None
        #: event index -> {id, name, q, quant, derived}
        self.events: List[Dict[str, Any]] = []
        self.event_index: Dict[str, int] = {}
        self.warnings: List[Dict[str, Any]] = []
        self.engine_warnings: List[Dict[str, Any]] = []
        self.tree_walk: Optional[float] = None
        self.reachable: List[bool] = []
        self.repeated: List[int] = []  # event indices reached by > 1 path
        self.non_coherent = False
        self.approximations: List[Dict[str, Any]] = []
        self._const: Dict[bool, int] = {}

    # ---- building --------------------------------------------------------

    def add(self, op: tuple, node_id: Optional[str] = None) -> int:
        self.ops.append(op)
        self.op_nodes.append(node_id)
        return len(self.ops) - 1

    def const(self, value: bool) -> int:
        value = bool(value)
        if value not in self._const:
            self._const[value] = self.add(("const", value))
        return self._const[value]

    def var(self, node: Dict[str, Any], analysis: Dict[str, Any]) -> int:
        eid = str(node.get("id"))
        if eid in self.event_index:
            return self.events[self.event_index[eid]]["op"]
        try:
            q = float(node.get("probability", 0.0))
        except (TypeError, ValueError):
            q = 0.0
        if math.isnan(q):
            q = 0.0
        index = len(self.events)
        op = self.add(("var", index), eid)
        quant = node.get("quant")
        self.events.append({
            "id": eid,
            "name": str(node.get("name", "") or ""),
            "q": q,
            "op": op,
            "quant": copy.deepcopy(quant) if isinstance(quant, dict) else None,
            "derived": engine.derive_quant(node, analysis),
        })
        self.event_index[eid] = index
        return op

    # ---- readers ----------------------------------------------------------

    def event_ids(self) -> List[str]:
        return [e["id"] for e in self.events]

    def reachable_events(self) -> List[int]:
        """Event indices the top event depends on."""
        return [i for i, e in enumerate(self.events) if self.reachable[e["op"]]]

    def repeated_events(self) -> List[Dict[str, str]]:
        return [{"id": self.events[i]["id"], "name": self.events[i]["name"]}
                for i in self.repeated]

    def evaluate(self, q: Optional[List[float]] = None) -> float:
        """The engine's number for this graph with event probabilities ``q``
        (defaults to each event's own). Exact probability only when the tree
        has no repeated events."""
        if self.top is None:
            return 0.0
        qs = q if q is not None else [e["q"] for e in self.events]
        vals: List[float] = [0.0] * len(self.ops)
        for i, op in enumerate(self.ops):
            if not self.reachable[i]:
                continue
            vals[i] = eval_op(op, vals, qs)
        return vals[self.top]


def eval_op(op: tuple, vals: List[float], qs: List[float]) -> float:
    """One operator with the engine's gate formulas."""
    kind = op[0]
    if kind == "var":
        return qs[op[1]]
    if kind == "const":
        return 1.0 if op[1] else 0.0
    if kind == "and":
        result = 1.0
        for r in op[1]:
            result *= vals[r]
        return result
    if kind == "or":
        return engine.or_probability([vals[r] for r in op[1]])
    if kind == "kofn":
        return engine.kofn_probability([vals[r] for r in op[2]], op[1])
    if kind == "xor":
        return engine.xor_probability([vals[r] for r in op[1]])
    if kind == "pand":
        result = 1.0
        for r in op[1]:
            result *= vals[r]
        return engine.pand_divide(result, len(op[1]))
    raise ValueError("unknown op %r" % (kind,))


def _gate_type(node: Dict[str, Any]) -> Optional[str]:
    raw = node.get("gateType")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().upper()
    return None


def recalculated_core(tree: Dict[str, Any], analysis: Optional[Dict[str, Any]]):
    """A WebCore holding a deep copy of ``tree``, recalculated in FTA mode."""
    core = engine.WebCore()
    core.set_data(copy.deepcopy(tree) if isinstance(tree, dict) else {})
    core.analysis, _problems = engine.coerce_analysis(analysis)
    core.mode = "FTA"
    core.recalculate_probabilities()
    return core


def compile_tree(tree: Dict[str, Any], analysis: Optional[Dict[str, Any]] = None
                 ) -> Structure:
    """Compile ``tree`` (not modified) into a :class:`Structure`."""
    core = recalculated_core(tree, analysis)
    return compile_core(core)


def compile_core(core) -> Structure:
    """Compile an already recalculated ``WebCore``."""
    s = Structure()
    data = core.get_data()
    s.engine_warnings = copy.deepcopy(getattr(core, "quant_warnings", []) or [])
    if not isinstance(data, dict) or not data:
        s.reachable = []
        return s
    analysis = core.analysis
    s.tree_walk = data.get("calculatedProbability")

    index: Dict[str, Dict[str, Any]] = {}
    for node in core._walk(data):
        index.setdefault(str(node.get("id")), node)

    memo: Dict[int, int] = {}
    visiting = set()
    gate_only: Dict[int, int] = {}

    def warn(code: str, node: Dict[str, Any], **params: Any) -> None:
        s.warnings.append({"code": code, "nodeId": str(node.get("id")), "params": params})

    def leaf_ref(node: Dict[str, Any]) -> int:
        if str(node.get("eventKind") or "").lower() == "house":
            return s.const(node.get("houseState") is True)
        return s.var(node, analysis)

    # Recursion mirrors the engine's (which is recursive too), so the depth
    # limit is the same one the engine already lives with.
    def build(node: Dict[str, Any]) -> Optional[int]:
        key = id(node)
        if key in memo:
            return memo[key]
        if key in visiting:
            if key in gate_only:
                return gate_only[key]
            if _gate_type(node) == "TRANSFER":
                return None
            if not (node.get("children") or []):
                return leaf_ref(node)
            return None

        visiting.add(key)
        nid = str(node.get("id"))
        children = node.get("children", []) or []
        gate_type = _gate_type(node)

        if gate_type == "TRANSFER":
            for child in children:
                build(child)
            target_id = node.get("transferTo")
            target = index.get(str(target_id)) if target_id not in (None, "") else None
            if target is None or target is node:
                warn("TRANSFER_MISSING", node, transferTo=target_id)
                base = s.const(False)
            else:
                value = build(target)
                if value is None:
                    warn("TRANSFER_CYCLE", node, transferTo=target_id)
                    base = s.const(False)
                else:
                    base = value
        elif not children:
            base = leaf_ref(node)
        else:
            refs = []
            for child in children:
                ref = build(child)
                if ref is None:
                    warn("CYCLIC_LINK", node, childId=str(child.get("id")))
                else:
                    refs.append(ref)
            refs_t = tuple(refs)
            if gate_type is None or gate_type not in _GATE_KINDS:
                gate_value = node.get("logicGate", "OR")
                gate = str(gate_value).strip().upper() if gate_value else "OR"
            else:
                gate = gate_type
            if gate in ("AND", "INHIBIT"):
                base = s.add(("and", refs_t), nid)
            elif gate == "KOFN":
                k = node.get("k")
                if isinstance(k, float) and k.is_integer():
                    k = int(k)
                if isinstance(k, bool) or not isinstance(k, int) or k < 1:
                    k = 1
                base = s.add(("kofn", k, refs_t), nid)
            elif gate == "XOR":
                base = s.add(("xor", refs_t), nid)
            elif gate == "PAND":
                base = s.add(("pand", refs_t), nid)
            else:
                base = s.add(("or", refs_t), nid)
        gate_only[key] = base

        and_refs = []
        or_refs = []
        for link in node.get("links", []) or []:
            tid = link.get("target_id")
            rel = (link.get("relation") or "OR").upper()
            if not tid:
                continue
            target = index.get(str(tid))
            if not target:
                continue
            ref = build(target)
            if ref is None:
                warn("CYCLIC_LINK", node, targetId=str(tid), relation=rel)
                continue
            (and_refs if rel == "AND" else or_refs).append(ref)
        if and_refs:
            base = s.add(("and", (base,) + tuple(and_refs)), nid)
        if or_refs:
            base = s.add(("or", (base,) + tuple(or_refs)), nid)

        memo[key] = base
        visiting.remove(key)
        gate_only.pop(key, None)
        return base

    top = build(data)
    s.top = top
    _analyse(s)
    return s


def _analyse(s: Structure) -> None:
    """Reachability, repeated events, non-coherence and approximations."""
    n = len(s.ops)
    paths = [0] * n
    s.reachable = [False] * n
    if s.top is None:
        return
    paths[s.top] = 1
    for i in range(n - 1, -1, -1):
        if not paths[i]:
            continue
        s.reachable[i] = True
        op = s.ops[i]
        kind = op[0]
        refs = op[2] if kind == "kofn" else (op[1] if kind in ("and", "or", "xor", "pand") else ())
        for r in refs:
            paths[r] = min(2, paths[r] + paths[i])
    s.repeated = [i for i, e in enumerate(s.events) if paths[e["op"]] >= 2]

    approximations: List[Dict[str, Any]] = []
    seen = set()

    def note(code: str, node_id: Optional[str], params: Dict[str, Any]) -> None:
        if (code, node_id) in seen:
            return
        seen.add((code, node_id))
        approximations.append({"code": code, "nodeId": node_id, "params": params})

    for i, op in enumerate(s.ops):
        if not s.reachable[i]:
            continue
        if op[0] == "xor":
            s.non_coherent = True
            note("NONCOHERENT_XOR", s.op_nodes[i], {"n": len(op[1])})
        elif op[0] == "pand":
            note("PAND_APPROX", s.op_nodes[i], {"n": len(op[1])})
    for w in s.engine_warnings:
        if w.get("code") in APPROX_CODES:
            note(w["code"], w.get("nodeId"), dict(w.get("params") or {}))
    s.approximations = approximations


def op_children(op: tuple) -> Tuple[int, ...]:
    kind = op[0]
    if kind == "kofn":
        return op[2]
    if kind in ("and", "or", "xor", "pand"):
        return op[1]
    return ()
