"""
Minimal cut sets by bottom-up MOCUS (workstream A).

:func:`compute` compiles the tree with :mod:`logic` and expands the formula
graph bottom-up, memoised per operator, so a subtree shared through links or
transfers is expanded once. A cut set is an ``int`` bitmask over the events.

* OR   -- union of the children's sets, then minimised.
* AND  -- pairwise OR-product (``a | b``), truncated *inside* the product:
  sets above ``maxOrder`` are dropped, sets below ``cutoff`` are dropped, and
  beyond ``maxCount`` only the most probable are kept. Truncating early is
  sound for order and cutoff because a superset never has a higher order or a
  higher probability; the count cap is an approximation and is reported.
* KOFN -- "at least k of n" by the recurrence
  ``S(i, j) = S(i-1, j) OR (S(i-1, j-1) AND X_i)``, which yields exactly the
  minimal sets of the C(n, k) AND-combinations without listing them; above
  ``KOFN_MAX_COMBINATIONS`` combinations the analysis is refused.
* XOR  -- read as OR (the result is flagged non-coherent); PAND as AND.
* Constants -- TRUE is the empty set, FALSE no set at all.

Minimisation sorts by order and keeps a set only when no kept set is a subset
of it; kept sets are indexed by their lowest bit so each check only looks at
sets that could possibly be subsets.

Probabilities: ``P(C) = Π q``; rare-event value ``ΣP``; min-cut upper bound
``1 - Π(1 - P)`` (in log space, so 1e-12 values keep their digits).
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple

try:  # normal package import: ``import fta_web.cutsets``
    from . import logic
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import logic  # type: ignore[no-redef]

KOFN_MAX_COMBINATIONS = 20000
DEFAULT_TIME_BUDGET_S = 30.0


class CutsetError(ValueError):
    """The cut sets cannot be produced. ``reason`` is ``kofn`` or ``time``."""

    def __init__(self, reason: str, message: str, node_id: Optional[str] = None,
                 params: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.reason = reason
        self.node_id = node_id
        self.params = params or {}


class _Expander:
    def __init__(self, structure: "logic.Structure", max_order: int, max_count: int,
                 cutoff: float, deadline: float):
        self.s = structure
        self.q = [e["q"] for e in structure.events]
        self.max_order = max_order
        self.max_count = max_count
        self.cutoff = cutoff
        self.deadline = deadline
        self.truncated_by = set()
        self.memo: Dict[int, List[int]] = {}
        self._pcache: Dict[int, float] = {0: 1.0}
        self._ticks = 0

    # ---- helpers ---------------------------------------------------------

    def check_time(self) -> None:
        self._ticks += 1
        if self._ticks & 255 == 0 and time.perf_counter() > self.deadline:
            raise CutsetError("time", "Cut set analysis exceeded its time budget.")

    def prob(self, mask: int) -> float:
        cached = self._pcache.get(mask)
        if cached is not None:
            return cached
        p = 1.0
        m = mask
        q = self.q
        while m:
            low = m & -m
            p *= q[low.bit_length() - 1]
            m ^= low
        self._pcache[mask] = p
        return p

    def keep(self, mask: int) -> bool:
        """Order / cutoff truncation for one candidate set."""
        if bin(mask).count("1") > self.max_order:
            self.truncated_by.add("order")
            return False
        if self.cutoff > 0:
            p = self.prob(mask)
            if p < self.cutoff:
                if p > 0:
                    self.truncated_by.add("cutoff")
                return False
        return True

    def minimise(self, masks) -> List[int]:
        unique = set(masks)
        if 0 in unique:
            return [0]
        ordered = sorted(unique, key=lambda m: (bin(m).count("1"), m))
        by_low: Dict[int, List[int]] = {}
        kept: List[int] = []
        for m in ordered:
            self.check_time()
            rest = m
            dominated = False
            while rest and not dominated:
                low = rest & -rest
                rest ^= low
                bucket = by_low.get(low)
                if bucket:
                    for k in bucket:
                        if k & m == k:
                            dominated = True
                            break
            if not dominated:
                kept.append(m)
                by_low.setdefault(m & -m, []).append(m)
        return self.cap(kept)

    def cap(self, masks: List[int]) -> List[int]:
        if len(masks) <= self.max_count:
            return masks
        self.truncated_by.add("count")
        ranked = sorted(masks, key=lambda m: (-self.prob(m), bin(m).count("1"), m))
        return ranked[: self.max_count]

    def product(self, left: List[int], right: List[int]) -> List[int]:
        if not left or not right:
            return []
        out = set()
        for a in left:
            for b in right:
                self.check_time()
                m = a | b
                if m in out:
                    continue
                if self.keep(m):
                    out.add(m)
        return self.minimise(out)

    def union(self, lists) -> List[int]:
        merged = []
        for sets in lists:
            merged.extend(sets)
        return self.minimise(merged)

    # ---- expansion -------------------------------------------------------

    def run(self) -> List[int]:
        s = self.s
        if s.top is None:
            return []
        for i, op in enumerate(s.ops):
            if not s.reachable[i]:
                continue
            self.memo[i] = self.expand(i, op)
            # Free children no longer needed? The graph is small; keep all.
        return self.memo[s.top]

    def expand(self, i: int, op: tuple) -> List[int]:
        kind = op[0]
        memo = self.memo
        if kind == "var":
            mask = 1 << op[1]
            return [mask] if self.keep(mask) else []
        if kind == "const":
            return [0] if op[1] else []
        if kind in ("or", "xor"):
            return self.union(memo[r] for r in op[1])
        if kind in ("and", "pand"):
            refs = sorted(op[1], key=lambda r: len(memo[r]))
            acc = [0]
            for r in refs:
                acc = self.product(acc, memo[r])
                if not acc:
                    break
            return acc
        if kind == "kofn":
            k, refs = op[1], op[2]
            n = len(refs)
            if k > n:
                return []
            combos = math.comb(n, k)
            if combos > KOFN_MAX_COMBINATIONS:
                raise CutsetError(
                    "kofn",
                    "A %d-of-%d voting gate expands to %d combinations (limit %d)."
                    % (k, n, combos, KOFN_MAX_COMBINATIONS),
                    self.s.op_nodes[i],
                    {"k": k, "n": n, "combinations": combos,
                     "limit": KOFN_MAX_COMBINATIONS},
                )
            # row[j] = sets for "at least j of the inputs seen so far"
            row: List[List[int]] = [[0]] + [[] for _ in range(k)]
            for idx, r in enumerate(refs, start=1):
                x = memo[r]
                for j in range(min(idx, k), 0, -1):
                    with_x = self.product(row[j - 1], x) if row[j - 1] else []
                    if with_x:
                        row[j] = self.union((row[j], with_x))
            return row[k]
        raise ValueError("unknown op %r" % (kind,))


def _limits(analysis: Optional[Dict[str, Any]], limits: Optional[Dict[str, Any]]
            ) -> Tuple[int, int, float, float]:
    base = {}
    if isinstance(analysis, dict) and isinstance(analysis.get("cutsets"), dict):
        base.update(analysis["cutsets"])
    for key, value in (limits or {}).items():
        if value is not None:
            base[key] = value
    defaults = logic.engine.DEFAULT_ANALYSIS["cutsets"]
    max_order = int(base.get("maxOrder") or defaults["maxOrder"])
    max_count = int(base.get("maxCount") or defaults["maxCount"])
    cutoff = base.get("cutoff")
    cutoff = float(defaults["cutoff"] if cutoff is None else cutoff)
    budget = base.get("timeBudgetS")
    budget = float(DEFAULT_TIME_BUDGET_S if budget is None else budget)
    return max(1, max_order), max(1, max_count), max(0.0, cutoff), max(0.01, budget)


def mcub_of(probs) -> float:
    """``1 - Π(1 - P)`` in log space; any P >= 1 makes it 1."""
    acc = 0.0
    for p in probs:
        if p >= 1.0:
            return 1.0
        if p > 0.0:
            acc += math.log1p(-p)
    return -math.expm1(acc)


def compute(tree: Dict[str, Any], analysis: Optional[Dict[str, Any]] = None,
            limits: Optional[Dict[str, Any]] = None,
            structure: Optional["logic.Structure"] = None) -> Dict[str, Any]:
    """Minimal cut sets of ``tree`` (plain dicts in and out; ``tree`` is not
    modified). ``limits`` overrides ``analysis.cutsets`` (``maxOrder``,
    ``maxCount``, ``cutoff``) and adds ``timeBudgetS``.

    Raises :class:`CutsetError` when a voting gate is too large or the time
    budget runs out.
    """
    started = time.perf_counter()
    max_order, max_count, cutoff, budget = _limits(analysis, limits)
    s = structure if structure is not None else logic.compile_tree(tree, analysis)
    expander = _Expander(s, max_order, max_count, cutoff, started + budget)
    masks = expander.run()

    rows = []
    for m in masks:
        p = expander.prob(m)
        indices = []
        rest = m
        while rest:
            low = rest & -rest
            indices.append(low.bit_length() - 1)
            rest ^= low
        rows.append((p, len(indices), indices))
    rows.sort(key=lambda r: (-r[0], r[1], [s.events[i]["name"] for i in r[2]]))
    rare = sum(r[0] for r in rows)
    mcub = mcub_of(r[0] for r in rows)

    cut_sets = []
    for rank, (p, order, indices) in enumerate(rows, start=1):
        events = [{"id": s.events[i]["id"], "name": s.events[i]["name"],
                   "q": s.events[i]["q"]} for i in indices]
        events.sort(key=lambda e: (e["name"], e["id"]))
        cut_sets.append({
            "rank": rank,
            "events": events,
            "order": order,
            "probability": p,
            "share": (p / rare) if rare > 0 else 0.0,
        })

    truncated_by = sorted(expander.truncated_by)
    warnings = list(s.warnings)
    if truncated_by:
        warnings.append({"code": "CUTSETS_TRUNCATED", "nodeId": None,
                         "params": {"by": truncated_by, "maxOrder": max_order,
                                    "maxCount": max_count, "cutoff": cutoff}})
    return {
        "cutSets": cut_sets,
        "total": len(cut_sets),
        "truncated": bool(truncated_by),
        "truncatedBy": truncated_by,
        "mcub": mcub,
        "rareEvent": rare,
        "treeWalk": s.tree_walk,
        "repeatedEvents": s.repeated_events(),
        "nonCoherent": s.non_coherent,
        "approximations": s.approximations,
        "warnings": warnings,
        "limits": {"maxOrder": max_order, "maxCount": max_count, "cutoff": cutoff},
        "elapsedMs": round((time.perf_counter() - started) * 1000.0, 1),
    }
