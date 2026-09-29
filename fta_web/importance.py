"""
Importance measures on the min-cut upper bound (workstream A).

``Q = 1 - Π_j (1 - P_j)`` over the minimal cut sets of a
:func:`cutsets.compute` result, and for each event ``i``:

* Birnbaum         ``Q(q_i=1) - Q(q_i=0)``
* Fussell-Vesely   ``(Q - Q(q_i=0)) / Q``
* RAW              ``Q(q_i=1) / Q``
* RRW              ``Q / Q(q_i=0)`` -- infinite when removing the event makes
  the top event impossible: then ``rrw`` is None and ``rrwInfinite`` True.

Each ``Q(q_i=x)`` only changes the cut sets that contain ``i``, so an inverted
index event -> cut sets makes the whole table O(total cut-set size). The
products ``Π(1-P)`` are kept in log space as ``(zeros, log-sum)`` pairs -- a
cut set with ``P = 1`` is a zero factor that a plain log cannot hold -- and
differences such as ``Q - Q0`` are formed as ``exp(L0)·(-expm1(L - L0))`` so
small contributions keep their digits.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

_LogProd = Tuple[int, float]  # (number of zero factors, sum of logs of the rest)


def _factor(p: float) -> _LogProd:
    """log(1 - p) as a (zeros, log) pair."""
    if p >= 1.0:
        return (1, 0.0)
    if p <= 0.0:
        return (0, 0.0)
    return (0, math.log1p(-p))


def _exp(lp: _LogProd) -> float:
    return 0.0 if lp[0] > 0 else math.exp(lp[1])


def _diff(a: _LogProd, b: _LogProd, delta: float) -> float:
    """exp(a) - exp(b), accurately when the two are close. ``delta`` is
    ``b[1] - a[1]`` computed directly from the few terms that differ: taking
    it as the difference of the two rounded sums would cancel (the sums can
    be ~1 while their difference is ~1e-17)."""
    if a[0] > 0 and b[0] > 0:
        return 0.0
    if a[0] > 0:
        return -math.exp(b[1])
    if b[0] > 0:
        return math.exp(a[1])
    return math.exp(a[1]) * (-math.expm1(delta))


def _partials(values) -> List[float]:
    """Non-overlapping partial sums whose exact total is Σ values
    (Shewchuk; the recipe ``math.fsum`` is built on)."""
    partials: List[float] = []
    for x in values:
        i = 0
        for y in partials:
            if abs(x) < abs(y):
                x, y = y, x
            hi = x + y
            lo = y - (hi - x)
            if lo:
                partials[i] = lo
                i += 1
            x = hi
        partials[i:] = [x]
    return partials


def _clean(value: Optional[float]) -> Optional[float]:
    if value is None or math.isnan(value) or math.isinf(value):
        return None
    return value


def compute(cutset_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """``[{id, name, q, fv, birnbaum, raw, rrw, rrwInfinite, cutSetCount}]``,
    sorted by FV (largest first), for every event in the cut sets."""
    cut_sets = cutset_result.get("cutSets") or []
    events: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    members: List[List[int]] = []  # cut set -> event indices
    for cs in cut_sets:
        idx = []
        for ev in cs.get("events") or []:
            eid = str(ev.get("id"))
            if eid not in events:
                events[eid] = {"id": eid, "name": ev.get("name", ""),
                               "q": float(ev.get("q") or 0.0), "index": len(order)}
                order.append(eid)
            idx.append(events[eid]["index"])
        members.append(idx)

    q = [events[eid]["q"] for eid in order]
    inverted: List[List[int]] = [[] for _ in order]
    factors: List[_LogProd] = []
    zeros = 0
    for j, idx in enumerate(members):
        p = 1.0
        for i in idx:
            p *= q[i]
            inverted[i].append(j)
        f = _factor(p)
        factors.append(f)
        zeros += f[0]
    # The log-sum is held exactly (Shewchuk partials), so taking an event's
    # cut sets back out of it leaves no rounding residue: Q(q_i=0) of 1e-17
    # must not come out as the noise of a 1e-2 sum.
    partials = _partials(f[1] for f in factors)
    base: _LogProd = (zeros, math.fsum(partials))  # log(1 - Q)
    top = 1.0 - _exp(base) if base[0] else -math.expm1(base[1])

    def with_value(i: int, x: float) -> Tuple[_LogProd, List[float]]:
        """log(1 - Q(q_i = x)) and the change against ``base`` as terms."""
        z = zeros
        change: List[float] = []
        for j in inverted[i]:
            z -= factors[j][0]
            change.append(-factors[j][1])
            rest = 1.0
            for other in members[j]:
                if other != i:
                    rest *= q[other]
            f = _factor(rest * x)
            z += f[0]
            change.append(f[1])
        return (z, math.fsum(partials + change)), change

    out = []
    for eid in order:
        info = events[eid]
        i = info["index"]
        l0, change0 = with_value(i, 0.0)
        l1, change1 = with_value(i, 1.0)
        q0 = 1.0 - _exp(l0) if l0[0] else -math.expm1(l0[1])
        q1 = 1.0 - _exp(l1) if l1[0] else -math.expm1(l1[1])
        # Q1 - Q0 = (1-Q0) - (1-Q1); Q - Q0 = (1-Q0) - (1-Q). The exponent
        # differences come straight from the changed terms (exact via fsum).
        birnbaum = _diff(l0, l1, math.fsum(change1 + [-t for t in change0]))
        reduction = _diff(l0, base, math.fsum([-t for t in change0]))
        fv = reduction / top if top > 0 else None
        raw = q1 / top if top > 0 else None
        rrw_infinite = False
        if q0 > 0:
            rrw = top / q0
        else:
            rrw = None
            rrw_infinite = top > 0
        out.append({
            "id": eid,
            "name": info["name"],
            "q": info["q"],
            "fv": _clean(max(0.0, min(1.0, fv)) if fv is not None else None),
            "birnbaum": _clean(max(0.0, birnbaum)),
            "raw": _clean(raw),
            "rrw": _clean(rrw),
            "rrwInfinite": rrw_infinite,
            "cutSetCount": len(inverted[i]),
        })
    out.sort(key=lambda r: (-(r["fv"] if r["fv"] is not None else -1.0), r["name"], r["id"]))
    return out
