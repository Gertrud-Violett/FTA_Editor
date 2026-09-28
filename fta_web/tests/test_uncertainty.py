"""
Tests for fta_web/uncertainty.py: seeded determinism, lognormal parameter
recovery, the rate models, both evaluation methods, the time cap, and speed.
"""
import copy
import math
import random
import time

import pytest

from fta_web import cutsets, uncertainty
from fta_web.engine import WebCore


def leaf(node_id, p, **extra):
    node = {"id": node_id, "name": node_id, "probability": p, "links": [], "children": []}
    node.update(extra)
    return node


def unc(median=None, ef=3.0, mean=None, model="fixed", **params):
    quant = {"model": model, "unc": {"dist": "lognormal", "ef": ef}}
    if median is not None:
        quant["unc"]["median"] = median
    if mean is not None:
        quant["unc"]["mean"] = mean
    quant.update(params)
    return quant


def two_event_tree():
    return {"id": "root", "name": "top", "logicGate": "OR", "links": [], "children": [
        leaf("A", 1e-3, quant=unc(1e-3, 3)),
        leaf("B", 2e-3, quant=unc(2e-3, 10)),
    ]}


def test_seeded_runs_are_deterministic():
    a = uncertainty.run(two_event_tree(), None, n=1500, seed=42)
    b = uncertainty.run(two_event_tree(), None, n=1500, seed=42)
    c = uncertainty.run(two_event_tree(), None, n=1500, seed=43)
    for key in ("mean", "median", "p05", "p95", "std", "histogram"):
        assert a[key] == b[key]
    assert a["mean"] != c["mean"]
    assert a["seed"] == 42 and a["completed"] == a["requested"] == 1500
    assert a["method"] == "tree"
    assert a["uncertainEvents"] == ["A", "B"] and a["certainEvents"] == []


def test_a_missing_seed_is_drawn_and_reported():
    first = uncertainty.run(two_event_tree(), None, n=300)
    assert isinstance(first["seed"], int)
    again = uncertainty.run(two_event_tree(), None, n=300, seed=first["seed"])
    assert again["mean"] == first["mean"]


def test_seed_and_n_default_from_analysis():
    analysis = {"mc": {"n": 700, "seed": 5}}
    out = uncertainty.run(two_event_tree(), analysis)
    assert out["requested"] == 700 and out["seed"] == 5


def _single(quant, p=1e-3):
    return {"id": "root", "name": "top", "logicGate": "OR", "links": [],
            "children": [leaf("A", p, quant=quant)]}


def test_lognormal_median_and_error_factor_recovery():
    out = uncertainty.run(_single(unc(1e-3, 3)), None, n=20000, seed=1)
    assert out["median"] == pytest.approx(1e-3, rel=0.03)
    assert out["p95"] / out["median"] == pytest.approx(3.0, rel=0.06)
    assert out["median"] / out["p05"] == pytest.approx(3.0, rel=0.06)
    sigma = math.log(3) / 1.645
    assert out["mean"] == pytest.approx(1e-3 * math.exp(sigma ** 2 / 2), rel=0.03)
    assert out["pointEstimate"] == pytest.approx(1e-3)


def test_mean_is_converted_to_the_median():
    sigma = math.log(5) / 1.645
    out = uncertainty.run(_single(unc(None, 5, mean=2e-3)), None, n=20000, seed=2)
    assert out["mean"] == pytest.approx(2e-3, rel=0.05)
    assert out["median"] == pytest.approx(2e-3 * math.exp(-sigma ** 2 / 2), rel=0.04)


def test_nominal_value_is_the_median_when_neither_is_given():
    out = uncertainty.run(_single(unc(None, 3), p=4e-3), None, n=10000, seed=3)
    assert out["median"] == pytest.approx(4e-3, rel=0.04)


def test_rate_model_samples_lambda():
    quant = unc(1e-4, 3, model="rate", **{"lambda": 1e-4, "T": 100})
    out = uncertainty.run(_single(quant, p=0.0), None, n=20000, seed=4)
    assert out["median"] == pytest.approx(-math.expm1(-1e-2), rel=0.03)
    assert out["pointEstimate"] == pytest.approx(-math.expm1(-1e-2))


def test_samples_are_clamped_to_one():
    out = uncertainty.run(_single(unc(0.6, 10), p=0.6), None, n=5000, seed=5)
    assert out["histogram"]["edges"][-1] <= 1.0
    assert out["p95"] == 1.0


def test_events_without_uncertainty_are_constants_and_reported():
    tree = two_event_tree()
    tree["children"].append(leaf("C", 0.5))
    out = uncertainty.run(tree, None, n=500, seed=1)
    assert out["certainEvents"] == ["C"]
    none = uncertainty.run({"id": "root", "name": "t", "logicGate": "AND", "links": [],
                            "children": [leaf("A", 0.1), leaf("B", 0.2)]}, None, n=100, seed=1)
    assert none["std"] == 0.0 and none["mean"] == pytest.approx(0.02)
    assert [w["code"] for w in none["warnings"]] == ["MC_NO_UNCERTAINTY"]


def test_tree_method_matches_the_engine_sample_for_sample():
    """With EF=1 the samples are the nominal values: the tree method must then
    reproduce the tree walk, KOFN, XOR-free links and all."""
    tree = {"id": "root", "name": "top", "logicGate": "OR", "links": [], "children": [
        {"id": "v", "name": "v", "gateType": "KOFN", "k": 2, "logicGate": "OR", "links": [],
         "children": [leaf("A", 0.1, quant=unc(0.1, 1)), leaf("B", 0.2, quant=unc(0.2, 1)),
                      leaf("C", 0.3, quant=unc(0.3, 1))]},
        {"id": "p", "name": "p", "gateType": "PAND", "logicGate": "AND", "links": [],
         "children": [leaf("D", 0.5), leaf("E", 0.4)]},
    ]}
    core = WebCore()
    core.set_data(copy.deepcopy(tree))
    core.recalculate_probabilities()
    out = uncertainty.run(tree, None, n=200, seed=9)
    assert out["method"] == "tree"
    assert out["mean"] == pytest.approx(core.get_data()["calculatedProbability"], rel=1e-9)
    assert out["std"] == pytest.approx(0.0, abs=1e-12)


def test_repeated_events_use_the_cut_sets():
    tree = {"id": "root", "name": "top", "logicGate": "OR", "links": [], "children": [
        {"id": "g1", "name": "g1", "logicGate": "AND", "links": [], "children": [
            leaf("A", 0.1, quant=unc(0.1, 1)), leaf("B", 0.2)]},
        {"id": "g2", "name": "g2", "logicGate": "AND", "links": [], "children": [
            {"id": "t", "name": "t", "gateType": "TRANSFER", "transferTo": "A",
             "links": [], "children": []}, leaf("C", 0.3)]},
    ]}
    out = uncertainty.run(tree, None, n=100, seed=1)
    assert out["method"] == "cutsets"
    assert out["repeatedEvents"] == [{"id": "A", "name": "A"}]
    expected = cutsets.compute(tree, None)["mcub"]
    assert out["mean"] == pytest.approx(expected, rel=1e-12)
    assert out["pointEstimate"] == pytest.approx(expected, rel=1e-12)


def test_cutset_method_against_a_direct_sampler():
    """Same seed, same draw order: a hand-written sampler over the cut sets
    must give the same distribution (checked on the quantiles)."""
    tree = {"id": "root", "name": "top", "logicGate": "XOR", "gateType": "XOR", "links": [],
            "children": [leaf("A", 0.01, quant=unc(0.01, 3)), leaf("B", 0.02, quant=unc(0.02, 3))]}
    out = uncertainty.run(tree, None, n=20000, seed=11)
    assert out["method"] == "cutsets" and out["nonCoherent"] is True
    rng = random.Random(123)
    sigma = math.log(3) / 1.645
    ref = sorted(1 - (1 - 0.01 * math.exp(sigma * rng.gauss(0, 1)))
                 * (1 - 0.02 * math.exp(sigma * rng.gauss(0, 1))) for _ in range(20000))
    assert out["median"] == pytest.approx(ref[10000], rel=0.03)
    assert out["p95"] == pytest.approx(ref[19000], rel=0.05)


def test_time_cap_returns_a_partial_result():
    out = uncertainty.run(two_event_tree(), None, n=100000, seed=1, time_limit=1e-6)
    assert out["truncatedByTime"] is True
    assert 0 < out["completed"] < 100000
    assert out["completed"] % uncertainty.CHUNK == 0
    assert out["mean"] is not None and sum(out["histogram"]["counts"]) == out["completed"]


def test_histogram_bins():
    lin = uncertainty.histogram([0.1, 0.2, 0.3, 0.4], bins=3)
    assert lin["logBins"] is False and sum(lin["counts"]) == 4 and len(lin["edges"]) == 4
    log = uncertainty.histogram([1e-6, 1e-5, 1e-4, 1e-3], bins=3)
    assert log["logBins"] is True and sum(log["counts"]) == 4
    assert log["edges"][1] == pytest.approx(1e-5) and log["edges"][2] == pytest.approx(1e-4)
    assert log["counts"][-1] >= 1 and log["counts"][0] >= 1
    same = uncertainty.histogram([0.5, 0.5], bins=10)
    assert same == {"edges": [0.5, 0.5], "counts": [2], "logBins": False}
    assert uncertainty.histogram([], 10)["counts"] == []


def test_wide_distribution_gets_log_bins():
    out = uncertainty.run(_single(unc(1e-4, 100)), None, n=3000, seed=1)
    assert out["histogram"]["logBins"] is True
    assert len(out["histogram"]["counts"]) == 40


def _big_tree(n_events=300, seed=0):
    rng = random.Random(seed)
    counter = [0]

    def build(depth):
        if depth == 3:
            counter[0] += 1
            eid = "e%d" % counter[0]
            return leaf(eid, 1e-3, quant=unc(rng.uniform(1e-4, 1e-2), rng.choice([3, 5, 10])))
        gate = rng.choice(["AND", "OR"])
        return {"id": "g%d_%d" % (depth, rng.randrange(10 ** 9)), "name": "g",
                "logicGate": gate, "links": [],
                "children": [build(depth + 1) for _ in range(rng.choice([6, 7]))]}

    tree = build(0)
    tree["id"] = "root"
    return tree, counter[0]


def test_speed_on_a_300_event_tree():
    tree, events = _big_tree()
    assert events >= 216
    started = time.perf_counter()
    out = uncertainty.run(tree, None, n=2000, seed=1)
    elapsed = time.perf_counter() - started
    assert out["method"] == "tree" and out["completed"] == 2000
    # Target: 10k samples in < 15 s, so 2k well inside 3 s (loose for CI).
    assert elapsed < 6.0, elapsed
