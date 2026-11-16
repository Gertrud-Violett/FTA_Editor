"""
Tests for fta_web/importance.py: every measure against a direct recomputation
of the min-cut upper bound with the event forced to 0 or 1 (the "finite
difference" of the definition), on hand-made and random cut-set lists.
"""
import math
import random

import pytest

from fta_web import cutsets, importance


def mcub(cut_sets, q):
    """The plain definition (log1p only so 1e-30 cut sets are not lost)."""
    acc = 0.0
    for cs in cut_sets:
        p = 1.0
        for eid in cs:
            p *= q[eid]
        if p >= 1.0:
            return 1.0
        acc += math.log1p(-p)
    return -math.expm1(acc)


def result_of(cut_sets, q):
    return {"cutSets": [
        {"events": [{"id": e, "name": e.upper(), "q": q[e]} for e in cs]} for cs in cut_sets
    ]}


def check(cut_sets, q):
    rows = importance.compute(result_of(cut_sets, q))
    top = mcub(cut_sets, q)
    assert {r["id"] for r in rows} == {e for cs in cut_sets for e in cs}
    for row in rows:
        eid = row["id"]
        q0 = mcub(cut_sets, dict(q, **{eid: 0.0}))
        q1 = mcub(cut_sets, dict(q, **{eid: 1.0}))
        assert row["q"] == q[eid]
        assert row["name"] == eid.upper()
        assert row["birnbaum"] == pytest.approx(q1 - q0, rel=1e-9, abs=1e-15)
        assert row["fv"] == pytest.approx((top - q0) / top, rel=1e-9, abs=1e-15)
        assert row["raw"] == pytest.approx(q1 / top, rel=1e-9)
        if q0 > 0:
            assert row["rrw"] == pytest.approx(top / q0, rel=1e-9)
            assert row["rrwInfinite"] is False
        else:
            assert row["rrw"] is None and row["rrwInfinite"] is True
        assert row["cutSetCount"] == sum(1 for cs in cut_sets if eid in cs)
    fvs = [r["fv"] for r in rows]
    assert fvs == sorted(fvs, reverse=True)
    return rows


def exact_measures(cut_sets, q):
    """Every measure in exact rational arithmetic (fractions of the floats)."""
    from fractions import Fraction

    qf = {k: Fraction(v) for k, v in q.items()}

    def top(fixed=None):
        prod = Fraction(1)
        for cs in cut_sets:
            p = Fraction(1)
            for eid in cs:
                p *= fixed[1] if fixed and eid == fixed[0] else qf[eid]
            prod *= 1 - p
        return 1 - prod

    base = top()
    out = {}
    for eid in {e for cs in cut_sets for e in cs}:
        q0, q1 = top((eid, Fraction(0))), top((eid, Fraction(1)))
        out[eid] = {"fv": float((base - q0) / base), "birnbaum": float(q1 - q0),
                    "raw": float(q1 / base), "rrw": float(base / q0) if q0 else None}
    return out


@pytest.mark.parametrize("seed", range(40))
def test_every_measure_to_full_relative_precision(seed):
    """B2B against exact rational arithmetic: small contributions must keep
    their digits. Before 1.7.1, L - L0 was the difference of two separately
    rounded log sums, which cancelled: in OR(A = 0.5, B = 1e-17) the FV of B
    came out 0.0 (exactly 1e-17), and the B2B oracle saw FV errors up to
    1.8e-8 relative on the corpus."""
    rng = random.Random(seed)
    events = ["e%d" % i for i in range(rng.randint(2, 7))]
    q = {e: rng.choice([0.5, 0.3, 0.1, 1e-3, 1e-7, 1e-12, 1e-17]) * rng.uniform(0.5, 1.5)
         for e in events}
    cut_sets = []
    for _ in range(rng.randint(1, 6)):
        cs = sorted(set(rng.sample(events, rng.randint(1, min(3, len(events))))))
        if cs not in cut_sets:
            cut_sets.append(cs)
    rows = {r["id"]: r for r in importance.compute(result_of(cut_sets, q))}
    for eid, want in exact_measures(cut_sets, q).items():
        got = rows[eid]
        for key in ("fv", "birnbaum", "raw"):
            assert got[key] == pytest.approx(want[key], rel=1e-12, abs=0), (eid, key, cut_sets, q)
        if want["rrw"] is None:
            assert got["rrwInfinite"] is True
        else:
            assert got["rrw"] == pytest.approx(want["rrw"], rel=1e-12, abs=0), (eid, cut_sets, q)


def test_a_tiny_contributor_keeps_its_fussell_vesely():
    q = {"a": 0.5, "b": 1e-17}
    rows = {r["id"]: r for r in importance.compute(result_of([["a"], ["b"]], q))}
    assert rows["b"]["fv"] == pytest.approx(1e-17 * 0.5 / (0.5 + 0.5e-17), rel=1e-12, abs=0)
    assert rows["b"]["rrw"] == pytest.approx(1 + 1e-17, rel=1e-15)
    assert rows["a"]["rrw"] == pytest.approx(0.5 / 1e-17, rel=1e-12)


def test_textbook():
    rows = check([["a", "b"], ["a", "c"]], {"a": 0.1, "b": 0.2, "c": 0.3})
    assert rows[0]["id"] == "a"
    assert rows[0]["fv"] == pytest.approx(1.0)
    assert rows[0]["rrwInfinite"] is True


def test_single_events_and_tiny_values():
    rows = check([["a"], ["b", "c"]], {"a": 1e-9, "b": 1e-5, "c": 2e-5})
    by_id = {r["id"]: r for r in rows}
    # Tiny contributions keep their digits (log-space differences).
    assert by_id["a"]["fv"] == pytest.approx(1e-9 / (1e-9 + 2e-10), rel=1e-6)
    assert by_id["b"]["birnbaum"] == pytest.approx(2e-5 * (1 - 1e-9), rel=1e-9)


def test_probability_one_cut_set():
    rows = check([["a"], ["b"]], {"a": 1.0, "b": 0.5})
    by_id = {r["id"]: r for r in rows}
    assert by_id["a"]["fv"] == pytest.approx(0.5)  # Q=1, Q(a=0)=0.5
    assert by_id["b"]["birnbaum"] == 0.0
    assert by_id["b"]["fv"] == 0.0


def test_zero_top():
    rows = importance.compute(result_of([["a"]], {"a": 0.0}))
    assert rows[0]["fv"] is None and rows[0]["raw"] is None
    assert rows[0]["rrw"] is None and rows[0]["rrwInfinite"] is False
    assert rows[0]["birnbaum"] == 1.0


def test_empty():
    assert importance.compute({"cutSets": []}) == []


@pytest.mark.parametrize("seed", range(40))
def test_random_cut_set_lists(seed):
    rng = random.Random(seed)
    names = ["e%d" % i for i in range(rng.randint(2, 9))]
    q = {n: rng.choice([rng.uniform(0.001, 0.5), 10 ** rng.uniform(-8, -2)]) for n in names}
    cut_sets = []
    for _ in range(rng.randint(1, 8)):
        cs = sorted(rng.sample(names, rng.randint(1, min(4, len(names)))))
        if cs not in cut_sets:
            cut_sets.append(cs)
    check(cut_sets, q)


def test_end_to_end_from_a_tree():
    tree = {"id": "root", "name": "top", "logicGate": "OR", "children": [
        {"id": "g", "name": "g", "logicGate": "AND", "children": [
            {"id": "A", "name": "A", "probability": 0.1, "children": []},
            {"id": "B", "name": "B", "probability": 0.2, "children": []}]},
        {"id": "C", "name": "C", "probability": 0.01, "children": []}]}
    result = cutsets.compute(tree, None)
    rows = importance.compute(result)
    assert [r["id"] for r in rows] == ["A", "B", "C"] or [r["id"] for r in rows] == ["B", "A", "C"]
    top = result["mcub"]
    assert top == pytest.approx(1 - 0.98 * 0.99)
    c = next(r for r in rows if r["id"] == "C")
    assert c["raw"] == pytest.approx(1 / top)
    assert math.isclose(c["fv"], (top - 0.02) / top, rel_tol=1e-9)
