"""
Tree validation rules for the Validation tab (1.7 workstream E).

``run(tree, analysis, session_warnings=(), mode="FTA", extra=None)`` returns a
list of plain-dict issues::

    {severity, code, nodeId, nodeName, message, params, hintKey}

``message`` is an English default with ``params`` interpolated; the UI
localises through ``val.code.<CODE>`` and shows the one-line fix
``val.fix.<CODE>`` (``hintKey``). ``tree`` and every argument are left
untouched: the rules run on a deep copy recalculated by ``engine.WebCore``, so
``calculatedProbability`` and the engine's ``quant_warnings`` are fresh.

Severities (frozen, deterministic -- one severity per code)
-----------------------------------------------------------
==========================  ========  ====  =========================================
code                        severity  mode  fires when
==========================  ========  ====  =========================================
DANGLING_LINK               error     FTA   a link's ``target_id`` is not in the tree
TRANSFER_MISSING            error     FTA   TRANSFER without an existing target (engine)
TRANSFER_CYCLE              error     FTA   a TRANSFER chain comes back on itself (engine)
INHIBIT_ARITY               error     FTA   INHIBIT without exactly 1 input + 1
                                            conditioning child
KOFN_ARITY                  error     FTA   KOFN with k missing, k < 1 or k > n
XOR_ARITY                   error     FTA   XOR without exactly 2 inputs
QUANT_PARAM_MISSING         error     FTA   a rate/standby/repairable model lacks a
                                            parameter (engine; the old value is kept)
CYCLIC_LINK                 warning   FTA   a link closes a loop (child edges + links);
                                            the engine skips it, so the result is
                                            approximate
TRANSFER_HAS_CHILDREN       warning   FTA   a TRANSFER has children (they are ignored)
HOUSE_HAS_CHILDREN          warning   FTA   a house event has children (its on/off
                                            state is ignored)
SINGLE_INPUT_GATE           warning   FTA   an AND/OR/PAND gate below the top event
                                            has one input and no links
DEFAULT_PROBABILITY         warning   FTA   a basic leaf is exactly 1.0 with no quant
                                            model -- most likely never quantified
PARENT_PROBABILITY_IGNORED  warning   FTA   a gate's own ``probability`` is neither 1.0
                                            nor its calculated value (it is ignored)
STANDBY_LARGE_LT            warning   FTA   standby λτ > 0.2 (engine)
NONCOHERENT_XOR             warning   FTA   the tree has an XOR gate (one issue, at the
                                            first XOR; cut sets are approximate)
CUTSETS_TRUNCATED           warning   FTA   ``extra["cutsets"]["truncated"]`` is truthy
ETA_BRANCH_SUM              warning   ETA   children's probabilities do not sum to 1
                                            (±1e-6)
LOAD_REPAIR                 warning   both  session warning, passed through
LINKS_REMOVED               warning   both  session warning, passed through
UNDEVELOPED_EVENT           info      FTA   a leaf marked ``eventKind: undeveloped``
PAND_APPROX                 info      FTA   PAND evaluated as AND × 1/n! (engine)
==========================  ========  ====  =========================================

Deliberate exemptions: the top event (``root``) is never SINGLE_INPUT_GATE
(a top event restating its one cause is normal practice) and a root with no
children is never DEFAULT_PROBABILITY (that is simply an empty document).
INHIBIT/KOFN/XOR/TRANSFER gates are not SINGLE_INPUT_GATE -- their own arity
codes cover them. In ETA mode links, gate kinds and quant models do not
take part in the calculation, so only ETA_BRANCH_SUM and the session warnings
are reported there.

Order: errors, warnings, info; within a severity, document-level issues
(``nodeId`` None) first, then tree pre-order, then issues whose node is no
longer in the tree; ties keep rule order. Engine warnings that repeat a rule
of lint's own (same code and node) are dropped.
"""
from __future__ import annotations

import copy
import math
import string
from typing import Any, Dict, Iterable, List, Optional

try:  # normal package import: ``import fta_web.lint``
    from .engine import WebCore, coerce_analysis
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    from engine import WebCore, coerce_analysis  # type: ignore[no-redef]


SEVERITIES = ("error", "warning", "info")

SEVERITY: Dict[str, str] = {
    "DANGLING_LINK": "error",
    "TRANSFER_MISSING": "error",
    "TRANSFER_CYCLE": "error",
    "INHIBIT_ARITY": "error",
    "KOFN_ARITY": "error",
    "XOR_ARITY": "error",
    "QUANT_PARAM_MISSING": "error",
    "CYCLIC_LINK": "warning",
    "TRANSFER_HAS_CHILDREN": "warning",
    "HOUSE_HAS_CHILDREN": "warning",
    "SINGLE_INPUT_GATE": "warning",
    "DEFAULT_PROBABILITY": "warning",
    "PARENT_PROBABILITY_IGNORED": "warning",
    "STANDBY_LARGE_LT": "warning",
    "NONCOHERENT_XOR": "warning",
    "CUTSETS_TRUNCATED": "warning",
    "ETA_BRANCH_SUM": "warning",
    "LOAD_REPAIR": "warning",
    "LINKS_REMOVED": "warning",
    "UNDEVELOPED_EVENT": "info",
    "PAND_APPROX": "info",
}

#: Every frozen code (the plan's list), in severity order.
CODES = tuple(SEVERITY)

MESSAGES: Dict[str, str] = {
    "DANGLING_LINK": "Link points to node '{targetId}', which does not exist.",
    "TRANSFER_MISSING": "Transfer gate has no valid target (transferTo = '{transferTo}').",
    "TRANSFER_CYCLE": "Transfer to '{transferTo}' leads back to itself; it is counted as 0.",
    "INHIBIT_ARITY": "INHIBIT gate needs exactly one input and one conditioning event "
                     "(has {n} children, {conditions} conditioning).",
    "KOFN_ARITY": "K-out-of-N gate needs 1 <= k <= n (k = {k}, n = {n}).",
    "XOR_ARITY": "XOR gate needs exactly 2 inputs (has {n}).",
    "QUANT_PARAM_MISSING": "The '{model}' model is missing: {missing}. "
                           "The previous probability is used.",
    "CYCLIC_LINK": "Link to '{targetName}' creates a loop; the calculation skips it, "
                   "so the result is approximate.",
    "TRANSFER_HAS_CHILDREN": "Transfer gate has {n} children; they are ignored.",
    "HOUSE_HAS_CHILDREN": "House event has {n} children; its on/off state is ignored.",
    "SINGLE_INPUT_GATE": "{gate} gate has only one input, so it does nothing.",
    "DEFAULT_PROBABILITY": "Probability is 1.0 (the default); this event is probably "
                           "not quantified yet.",
    "PARENT_PROBABILITY_IGNORED": "Entered probability {probability} is not used; the "
                                  "value comes from the inputs ({calculated}).",
    "STANDBY_LARGE_LT": "Standby λτ = {lambdaTau} is above 0.2; the λτ/2 approximation "
                        "is poor.",
    "NONCOHERENT_XOR": "The tree has {count} XOR gate(s); cut-set results are approximate.",
    "CUTSETS_TRUNCATED": "The cut-set list was truncated ({reason}); results may be "
                         "underestimated.",
    "ETA_BRANCH_SUM": "Branch probabilities under this node sum to {sum}, not 1.",
    "LOAD_REPAIR": "The file was repaired when it was loaded.",
    "LINKS_REMOVED": "Link from '{nodeId}' to deleted node '{targetId}' was removed.",
    "UNDEVELOPED_EVENT": "Undeveloped event: its causes are not analysed further.",
    "PAND_APPROX": "Priority-AND is approximated as AND × 1/{n}!.",
}

_SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}
_BASIC_GATES = ("AND", "OR", "PAND")
_ARITY_GATES = ("KOFN", "XOR", "INHIBIT")


# ---- helpers -------------------------------------------------------------------


class _Params(dict):
    """format_map mapping: a missing key renders as ``{key}``, floats as %.3g,
    lists joined."""

    def __missing__(self, key):
        return "{" + key + "}"

    def __getitem__(self, key):
        value = dict.__getitem__(self, key) if key in self else self.__missing__(key)
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, float):
            return "%.3g" % value
        if isinstance(value, (list, tuple)):
            return ", ".join(str(v) for v in value)
        if value is None:
            return "-"
        return value


_FORMATTER = string.Formatter()


def format_message(template: str, params: Dict[str, Any]) -> str:
    try:
        return _FORMATTER.vformat(template, (), _Params(params or {}))
    except (ValueError, IndexError, KeyError):
        return template


def _gate_type(node: Dict[str, Any]) -> Optional[str]:
    raw = node.get("gateType")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().upper()
    return None


def _effective_gate(node: Dict[str, Any]) -> str:
    gate_type = _gate_type(node)
    if gate_type in ("AND", "OR", "KOFN", "XOR", "INHIBIT", "PAND", "TRANSFER"):
        return gate_type
    value = node.get("logicGate", "OR")
    gate = str(value).strip().upper() if value else "OR"
    return "AND" if gate == "AND" else "OR"


def _event_kind(node: Dict[str, Any]) -> str:
    return str(node.get("eventKind") or "").strip().lower()


def _float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(number) else number


def _walk(root: Dict[str, Any]):
    stack = [root]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        yield node
        stack.extend(reversed(node.get("children") or []))


def _has_quant_model(node: Dict[str, Any]) -> bool:
    quant = node.get("quant")
    if not isinstance(quant, dict):
        return False
    return str(quant.get("model") or "fixed").lower() != "fixed"


# ---- link cycles ---------------------------------------------------------------


def _cyclic_links(nodes: List[Dict[str, Any]], index: Dict[str, Dict[str, Any]]):
    """(owner, link) for every link whose two ends lie in one strongly connected
    component of the child + link graph (i.e. the link closes a loop)."""
    pos = {id(n): i for i, n in enumerate(nodes)}
    adjacency: List[List[int]] = [[] for _ in nodes]
    any_link = False
    for i, node in enumerate(nodes):
        for child in node.get("children") or []:
            if id(child) in pos:
                adjacency[i].append(pos[id(child)])
        for link in node.get("links") or []:
            if not isinstance(link, dict):
                continue
            target = index.get(str(link.get("target_id"))) if link.get("target_id") else None
            if target is not None:
                adjacency[i].append(pos[id(target)])
                any_link = True
    if not any_link:
        return []

    # Iterative Tarjan.
    n = len(nodes)
    order = [-1] * n
    low = [0] * n
    on_stack = [False] * n
    comp = [-1] * n
    stack: List[int] = []
    counter = 0
    comp_count = 0
    for start in range(n):
        if order[start] != -1:
            continue
        work = [(start, 0)]
        order[start] = low[start] = counter
        counter += 1
        stack.append(start)
        on_stack[start] = True
        while work:
            v, i = work[-1]
            if i < len(adjacency[v]):
                work[-1] = (v, i + 1)
                w = adjacency[v][i]
                if order[w] == -1:
                    order[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on_stack[w] = True
                    work.append((w, 0))
                elif on_stack[w]:
                    low[v] = min(low[v], order[w])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[v])
            if low[v] == order[v]:
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    comp[w] = comp_count
                    if w == v:
                        break
                comp_count += 1

    result = []
    for i, node in enumerate(nodes):
        for link in node.get("links") or []:
            if not isinstance(link, dict) or not link.get("target_id"):
                continue
            target = index.get(str(link.get("target_id")))
            if target is None:
                continue
            j = pos[id(target)]
            if i == j or comp[i] == comp[j]:
                result.append((node, link, target))
    return result


# ---- the rules -----------------------------------------------------------------


def run(tree: Any, analysis: Optional[Dict[str, Any]] = None,
        session_warnings: Iterable[Dict[str, Any]] = (), mode: str = "FTA",
        extra: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Every issue for ``tree`` (see the module docstring). Never raises on a
    malformed tree; nothing passed in is modified."""
    mode = "ETA" if str(mode or "FTA").upper() == "ETA" else "FTA"
    issues: List[Dict[str, Any]] = []
    seen = set()

    root = copy.deepcopy(tree) if isinstance(tree, dict) else None
    nodes: List[Dict[str, Any]] = list(_walk(root)) if root else []
    index: Dict[str, Dict[str, Any]] = {}
    for node in nodes:
        index.setdefault(str(node.get("id")), node)

    def add(code: str, node: Optional[Dict[str, Any]], params: Optional[Dict[str, Any]] = None,
            message: Optional[str] = None, node_id: Any = None) -> None:
        nid = str(node.get("id")) if node is not None else (
            None if node_id is None else str(node_id))
        key = (code, nid)
        if code not in ("LOAD_REPAIR", "LINKS_REMOVED", "CYCLIC_LINK", "DANGLING_LINK"):
            if key in seen:
                return
        seen.add(key)
        params = dict(params or {})
        target = node if node is not None else index.get(nid) if nid is not None else None
        issues.append({
            "severity": SEVERITY.get(code, "warning"),
            "code": code,
            "nodeId": nid,
            "nodeName": target.get("name") if isinstance(target, dict) else None,
            "message": message if message else format_message(MESSAGES.get(code, code), params),
            "params": params,
            "hintKey": "val.fix." + code,
        })

    if root:
        core = WebCore()
        core.set_data(root)
        core.analysis, _problems = coerce_analysis(analysis)
        core.mode = mode
        try:
            core.recalculate_probabilities()
        except Exception:  # a malformed tree must not break validation
            pass

        if mode == "ETA":
            _eta_rules(nodes, add)
        else:
            _fta_rules(root, nodes, index, add, core, extra)

    for warning in session_warnings or ():
        if not isinstance(warning, dict):
            continue
        code = warning.get("code") or "LOAD_REPAIR"
        params = copy.deepcopy(warning.get("params") or {})
        message = warning.get("message") or format_message(MESSAGES.get(code, code), params)
        add(code, None, params, message=message, node_id=warning.get("nodeId"))

    order = {str(n.get("id")): i for i, n in reversed(list(enumerate(nodes)))}
    missing_pos = len(nodes)

    def sort_key(item):
        indexed = item[1]
        nid = indexed["nodeId"]
        pos = -1 if nid is None else order.get(nid, missing_pos)
        return (_SEV_RANK.get(indexed["severity"], 1), pos, item[0])

    return [issue for _i, issue in sorted(enumerate(issues), key=sort_key)]


def _eta_rules(nodes, add) -> None:
    for node in nodes:
        children = [c for c in (node.get("children") or []) if isinstance(c, dict)]
        if not children:
            continue
        total = math.fsum(_float(c.get("probability", 1.0), 1.0) for c in children)
        if abs(total - 1.0) > 1e-6:
            add("ETA_BRANCH_SUM", node, {"sum": total, "n": len(children)})


def _fta_rules(root, nodes, index, add, core, extra) -> None:
    root_key = id(root)
    xor_nodes = []

    for node in nodes:
        children = [c for c in (node.get("children") or []) if isinstance(c, dict)]
        links = [l for l in (node.get("links") or []) if isinstance(l, dict)]
        n = len(children)
        gate = _effective_gate(node)
        kind = _event_kind(node)

        for link in links:
            tid = link.get("target_id")
            if not tid or str(tid) not in index:
                add("DANGLING_LINK", node, {
                    "targetId": "" if tid is None else str(tid),
                    "relation": str(link.get("relation") or "OR").upper(),
                })

        if gate == "XOR" and n:
            xor_nodes.append(node)

        if gate == "TRANSFER":
            if n:
                add("TRANSFER_HAS_CHILDREN", node, {"n": n})
        elif n:
            if kind == "house":
                add("HOUSE_HAS_CHILDREN", node, {"n": n})
            if gate == "INHIBIT":
                conditions = sum(1 for c in children if _event_kind(c) == "conditioning")
                if conditions != 1 or n != 2:
                    add("INHIBIT_ARITY", node, {"conditions": conditions, "n": n})
            elif gate == "KOFN":
                k = node.get("k")
                if isinstance(k, float) and k.is_integer():
                    k = int(k)
                if isinstance(k, bool) or not isinstance(k, int) or k < 1 or k > n:
                    add("KOFN_ARITY", node, {"k": node.get("k"), "n": n})
            elif gate == "XOR":
                if n != 2:
                    add("XOR_ARITY", node, {"n": n})
            elif n == 1 and not links and id(node) != root_key:
                add("SINGLE_INPUT_GATE", node, {"gate": gate})

            prob = _float(node.get("probability", 1.0), 1.0)
            calc = node.get("calculatedProbability")
            if prob != 1.0 and isinstance(calc, (int, float)) and not isinstance(calc, bool):
                if not math.isclose(prob, float(calc), rel_tol=1e-9, abs_tol=1e-15):
                    add("PARENT_PROBABILITY_IGNORED", node,
                        {"probability": prob, "calculated": float(calc)})
        else:
            if kind == "undeveloped":
                add("UNDEVELOPED_EVENT", node)
            if (kind != "house" and id(node) != root_key and not _has_quant_model(node)
                    and _float(node.get("probability", 1.0), 1.0) == 1.0):
                add("DEFAULT_PROBABILITY", node)

    for owner, link, target in _cyclic_links(nodes, index):
        add("CYCLIC_LINK", owner, {
            "targetId": str(target.get("id")),
            "targetName": target.get("name"),
            "relation": str(link.get("relation") or "OR").upper(),
        })

    if xor_nodes:
        add("NONCOHERENT_XOR", xor_nodes[0], {
            "count": len(xor_nodes),
            "nodeIds": [str(x.get("id")) for x in xor_nodes],
        })

    # Engine findings (quant models, transfers, PAND); lint's own rules win.
    for warning in getattr(core, "quant_warnings", None) or []:
        code = warning.get("code")
        if code not in SEVERITY:
            continue
        add(code, index.get(str(warning.get("nodeId"))), warning.get("params") or {},
            node_id=warning.get("nodeId"))

    cutsets = (extra or {}).get("cutsets") if isinstance(extra, dict) else None
    if isinstance(cutsets, dict) and cutsets.get("truncated"):
        truncated = cutsets.get("truncated")
        reason = truncated if isinstance(truncated, str) else cutsets.get("truncatedBy")
        if isinstance(reason, (list, tuple)):
            reason = ", ".join(str(r) for r in reason)
        add("CUTSETS_TRUNCATED", None, {
            "reason": reason or "limits",
            "count": cutsets.get("count", len(cutsets.get("cutsets") or [])),
        })


def counts(issues: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    result = {severity: 0 for severity in SEVERITIES}
    for issue in issues:
        severity = issue.get("severity")
        result[severity if severity in result else "warning"] += 1
    return result
