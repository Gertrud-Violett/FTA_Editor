"""
Regression tests for the 1.7.0 backend debugging pass (pass 1: correctness
and robustness). Each test names the defect it pins; see the commit messages
for the root cause.
"""
import json
import math
import os
import random

import pytest

from fta_web import cutsets, engine, fsbrowser, importance, logic, uncertainty
from fta_web.engine import WebCore


def leaf(node_id, p, **extra):
    node = {"id": node_id, "name": node_id, "type": "Event", "probability": p,
            "logicGate": "OR", "notes": "", "links": [], "children": []}
    node.update(extra)
    return node


def gate(node_id, gate_type, children, **extra):
    node = {"id": node_id, "name": node_id, "type": "Event", "probability": 1.0,
            "logicGate": engine.project_logic_gate(gate_type),
            "notes": "", "links": [], "children": children}
    if gate_type not in ("AND", "OR"):
        node["gateType"] = gate_type
    node.update(extra)
    return node


def walk_value(tree, analysis=None):
    core = logic.recalculated_core(tree, analysis)
    return core.get_data()["calculatedProbability"]


# ---- PAND with more than 170 inputs -------------------------------------------------
# 171! does not fit a float, so ``product / math.factorial(n)`` raised
# OverflowError in the engine, the formula graph and the Monte Carlo sampler
# -- and the summary's tree-walk fallback re-raised it as a 500.


def big_pand(n=200, p=0.9):
    return gate("root", "PAND", [leaf("e%d" % i, p) for i in range(n)])


def test_pand_divide_matches_factorial_below_the_limit_and_survives_above():
    for n in (0, 1, 2, 5, 170):
        assert engine.pand_divide(0.5, n) == 0.5 / math.factorial(n)
    from fractions import Fraction

    exact = float(Fraction(1, 2 * math.factorial(171)))
    assert engine.pand_divide(0.5, 171) == pytest.approx(exact, rel=1e-6)
    assert engine.pand_divide(1.0, 500) == 0.0
    assert engine.pand_divide(0.0, 500) == 0.0


def test_pand_with_200_inputs_does_not_overflow_anywhere():
    tree = big_pand()
    assert walk_value(tree) == 0.0
    s = logic.compile_tree(tree, None)
    assert s.evaluate() == 0.0
    result = cutsets.compute(tree, None, {"maxOrder": 20})
    assert result["truncated"] is True  # a 200-event cut set is above maxOrder
    out = uncertainty.run(tree, None, n=20, seed=1)
    assert out["mean"] == 0.0
    summary = engine.summary(tree, None)
    assert summary["headline"] == 0.0


# ---- MCUB of no cut sets --------------------------------------------------------------


def test_mcub_of_nothing_is_positive_zero():
    value = cutsets.mcub_of([])
    assert value == 0.0 and math.copysign(1.0, value) == 1.0
    result = cutsets.compute(leaf("root", 0.0), None)
    assert json.dumps(result["mcub"]) == "0.0"


# ---- summary: document truncation vs the summary's own cap ---------------------------


def many_cut_sets(width=13):
    """AND of three ORs of ``width`` events: width**3 minimal cut sets."""
    return gate("root", "AND", [
        gate("g%d" % g, "OR", [leaf("e%d_%d" % (g, i), 0.01 * (i + 1)) for i in range(width)])
        for g in range(3)
    ])


def test_summary_cap_is_not_reported_as_document_truncation():
    tree = many_cut_sets()  # 2197 cut sets; the document allows 5000
    analysis = engine.default_analysis()
    full = cutsets.compute(tree, analysis)
    assert full["truncated"] is False and full["total"] == 13 ** 3
    out = engine.summary(tree, analysis)
    assert out["capped"] is True
    assert out["truncated"] is False and out["truncatedBy"] == []


def test_summary_uses_a_lower_document_max_count_and_reports_it():
    tree = many_cut_sets(5)  # 125 cut sets
    analysis = engine.merge_analysis(engine.default_analysis(), {"cutsets": {"maxCount": 100}})
    full = cutsets.compute(tree, analysis)
    assert full["truncated"] is True and full["total"] == 100
    out = engine.summary(tree, analysis)
    assert out["truncated"] is True and out["truncatedBy"] == ["count"]
    assert out["capped"] is False
    assert out["mcub"] == pytest.approx(full["mcub"])


def test_summary_without_truncation_has_the_new_fields():
    out = engine.summary(gate("root", "OR", [leaf("a", 0.1), leaf("b", 0.2)]), None)
    assert out["truncated"] is False and out["capped"] is False and out["truncatedBy"] == []


def test_summary_fallback_on_error_is_truncated_but_not_capped():
    tree = gate("root", "KOFN", [leaf("e%d" % i, 0.01) for i in range(30)], k=10)
    out = engine.summary(tree, None)
    assert out["truncated"] is True and out["capped"] is False
    assert out["headlineMethod"] == "treeWalk" and out["mcub"] is None


def test_summary_timeout_is_capped(monkeypatch):
    def slow(*_args, **_kwargs):
        raise cutsets.CutsetError("time", "Cut set analysis exceeded its time budget.")

    monkeypatch.setattr(cutsets, "compute", slow)
    out = engine.summary(gate("root", "OR", [leaf("a", 0.1)]), None)
    assert out["truncated"] is True and out["capped"] is True
    assert out["headline"] == pytest.approx(0.1)


# ---- Monte Carlo with an extreme error factor ----------------------------------------
# EF is only bounded below (>= 1) by the schema, and a loaded file is not
# validated at all: exp(sigma * z) overflowed (OverflowError -> 500).


@pytest.mark.parametrize("unc", [
    {"dist": "lognormal", "ef": 1e308, "mean": 0.1},
    {"dist": "lognormal", "ef": 1e308, "median": 0.1},
    {"dist": "lognormal", "ef": 1e30, "median": 1e300},
])
def test_uncertainty_survives_an_extreme_error_factor(unc):
    for model in ({"model": "fixed"}, {"model": "rate", "lambda": 1e-4},
                  {"model": "repairable", "lambda": 1e-3, "mu": 0.1},
                  {"model": "standby", "lambda": 1e-4, "tau": 100}):
        quant = dict(model, unc=unc)
        tree = gate("root", "OR", [leaf("a", 0.1, quant=quant), leaf("b", 0.2)])
        out = uncertainty.run(tree, None, n=500, seed=3)
        assert out["completed"] == 500
        for key in ("mean", "median", "p05", "p95", "std"):
            assert out[key] is not None and 0.0 <= out[key] <= 1.0 or key == "std"
            assert not math.isnan(out[key])


def test_repairable_sample_at_the_overflow_edge_is_one_not_zero():
    """x / (x + mu) with an enormous sampled lambda is 1, never NaN -> 0."""
    unc = {"dist": "lognormal", "ef": 1e300, "median": 1e300}
    quant = {"model": "repairable", "lambda": 1e-3, "mu": 0.1, "unc": unc}
    out = uncertainty.run(leaf("root", 0.1, quant=quant), None, n=400, seed=5)
    # Half the samples of a median-1e300 lambda are at or above 1e300.
    assert out["p95"] == 1.0


# ---- filesystem sandbox: Windows path forms ---------------------------------------------

windows_only = pytest.mark.skipif(os.name != "nt", reason="Windows path semantics")


@windows_only
@pytest.mark.parametrize("raw", ["notes.txt:evil.json", "notes.txt:x:$DATA.json",
                                 "sub\\notes.txt:evil.json"])
def test_alternate_data_streams_are_rejected(tmp_path, raw):
    """``notes.txt:evil.json`` passed the .json allow-list and wrote a hidden
    NTFS alternate data stream onto an arbitrary file inside the root."""
    (tmp_path / "notes.txt").write_text("secret")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "notes.txt").write_text("secret")
    root = fsbrowser.resolve_root(tmp_path)
    with pytest.raises(fsbrowser.PathRejected) as info:
        fsbrowser.resolve_in_root(raw, root)
    assert info.value.reason == "stream"
    with pytest.raises(fsbrowser.PathRejected):
        fsbrowser.resolve_for_write(raw, root, {".json"})


@windows_only
@pytest.mark.parametrize("raw", ["\\\\attacker.invalid\\share\\x.json",
                                 "//attacker.invalid/share/x.json",
                                 "\\\\?\\UNC\\attacker.invalid\\share\\x.json"])
def test_unc_paths_are_rejected_before_touching_the_network(tmp_path, monkeypatch, raw):
    """Resolving a UNC path opens it -- an SMB connection (and an NTLM
    handshake) to whatever host the client named -- before containment was
    checked. The drive must be compared lexically first."""
    root = fsbrowser.resolve_root(tmp_path)
    seen = []
    original = type(root).resolve

    def spy(self, *args, **kwargs):
        seen.append(str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(type(root), "resolve", spy)
    with pytest.raises(fsbrowser.PathRejected) as info:
        fsbrowser.resolve_in_root(raw, root)
    assert info.value.reason == "outside_root"
    assert not any("attacker" in s for s in seen)


@windows_only
def test_ordinary_windows_paths_still_work(tmp_path):
    root = fsbrowser.resolve_root(tmp_path)
    (tmp_path / "a.json").write_text("{}")
    assert fsbrowser.resolve_in_root(str(tmp_path / "a.json"), root) == root / "a.json"
    # Drive letter case and forward slashes are the same place.
    other_case = str(root / "a.json")
    other_case = other_case[0].swapcase() + other_case[1:]
    assert fsbrowser.resolve_in_root(other_case.replace("\\", "/"), root) == root / "a.json"
    assert fsbrowser.resolve_for_write("new.json", root, {".json"}) == root / "new.json"
