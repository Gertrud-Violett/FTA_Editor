"""F0 BRIEF criterion 7: the derived cut-set counts of the CCF fixtures.

The tests build, with no help from the generator, the SPEC 7.6 base tree and a
hand-expanded copy of it for the beta fixture and for the alpha fixture (each
CCF member replaced by OR(independent part, shared CCF basic events), the
probabilities from SPEC 7.3), run both through the current
``fta_web.cutsets.compute`` and then check

* that the expansion technique reproduces the reference cases R1/R1h/R2/R2h of
  SPEC 7.4 on a tiny tree (these pass without any F0 work),
* that every CCF event (10 beta, 55 alpha) appears in a derived cut set,
* that the committed fixture trees are the base tree of SPEC 7.6,
* that the totals and ``truncatedBy`` recorded as constants in
  ``fta_web/tests/fixtures/make_perf_fixtures.py`` are the derived ones.
"""
import importlib.util
import itertools
import json
import math
from pathlib import Path

import pytest

from fta_web import cutsets

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
GENERATOR = FIXTURES / "make_perf_fixtures.py"
CCF_FIXTURE = FIXTURES / "perf_ccf_301.json"
ALPHA_FIXTURE = FIXTURES / "perf_alpha_301.json"

SETTINGS = {"cutsets": {"maxOrder": 6, "maxCount": 5000, "cutoff": 1e-30}}
LIMITS = {"timeBudgetS": 120}  # generous: a slow PC must not truncate by time

# SPEC 7.6: AND modules under the OR subsystems S0, S2, S4.
BETA_MODULES = [(0, 1), (0, 3), (0, 5), (2, 1), (2, 3), (2, 5), (4, 1), (4, 3), (4, 5)]
BETA_GROUPS = [
    {"id": "G%d" % (k + 1), "members": ["C%d_%d_%d" % (i, j, m) for m in range(3)]}
    for k, (i, j) in enumerate(BETA_MODULES)
] + [{"id": "G10", "members": ["C4_5_3", "C4_5_4", "C4_5_5"]}]
BETA = 0.1

ALPHA_MODULES = [(0, 1), (0, 3), (0, 5), (2, 1), (2, 3)]
ALPHA_GROUPS = [
    {"id": "A%d" % (k + 1), "members": ["C%d_%d_%d" % (i, j, m) for m in range(4)]}
    for k, (i, j) in enumerate(ALPHA_MODULES)
]
ALPHA = (0.95, 0.03, 0.01, 0.01)


# --------------------------------------------------------------------------
# tree builders (written from SPEC 7.6 / 7.3, not from the generator)
# --------------------------------------------------------------------------


def leaf(node_id, q, name=None):
    return {"id": node_id, "name": name or node_id, "type": "Event",
            "logicGate": "OR", "probability": q, "links": [], "children": [],
            "quant": {"model": "fixed"}}


def gate(node_id, kind, children, type_="Event"):
    return {"id": node_id, "name": node_id, "type": type_, "logicGate": kind,
            "probability": 1.0, "links": [], "children": children}


def base_tree(member_ids=()):
    """The 301-node tree of SPEC 7.6; members listed in ``member_ids`` get
    q = 1e-3, every other component q = 1e-3 * (m + 1)."""
    members = set(member_ids)
    subsystems = []
    for i in range(6):
        modules = []
        for j in range(7):
            comps = []
            for m in range(6):
                cid = "C%d_%d_%d" % (i, j, m)
                comps.append(leaf(cid, 1e-3 if cid in members else 1e-3 * (m + 1)))
            modules.append(gate("M%d_%d" % (i, j), "AND" if (i + j) % 2 else "OR", comps))
        subsystems.append(gate("S%d" % i, "AND" if i % 2 else "OR", modules))
    return gate("root", "OR", subsystems, type_="Root")


def replace_leaves(node, make):
    """Copy of ``node`` where every leaf whose id ``make`` knows is replaced."""
    if not node["children"]:
        replaced = make(node)
        return replaced if replaced is not None else dict(node)
    copy_ = dict(node)
    copy_["children"] = [replace_leaves(child, make) for child in node["children"]]
    return copy_


def expand_beta(tree, groups, beta):
    """SPEC 7.3 beta factor: member -> OR(independent part (1 - beta) * Q_t,
    the group's one shared event ``ccf:<id>`` with beta * Q_t)."""
    owner = {m: g["id"] for g in groups for m in g["members"]}

    def make(node):
        gid = owner.get(node["id"])
        if gid is None:
            return None
        qt = node["probability"]
        return gate("ccfgate:" + node["id"], "OR", [
            leaf(node["id"], (1.0 - beta) * qt, node["name"]),
            leaf("ccf:" + gid, beta * qt, "CCF " + gid),  # same id under every member
        ])

    return replace_leaves(tree, make)


def expand_alpha_staggered(tree, groups, alpha):
    """SPEC 7.3 staggered alpha: Q_k = alpha_k / C(m-1, k-1) * Q_t, one event per
    member subset of size k >= 2, id ``ccf:<group>:<m1>+<m2>...``; member ->
    OR(independent part with Q_1, every CCF event that contains the member)."""
    by_member = {}
    for g in groups:
        members = g["members"]
        size = len(members)
        assert size == len(alpha)
        for k in range(2, size + 1):
            for subset in itertools.combinations(members, k):
                event_id = "ccf:%s:%s" % (g["id"], "+".join(subset))
                for member in subset:
                    by_member.setdefault(member, []).append((event_id, k, size))
        for member in members:
            by_member.setdefault(member, [])

    def make(node):
        events = by_member.get(node["id"])
        if events is None:
            return None
        qt = node["probability"]
        children = [leaf(node["id"], alpha[0] / math.comb(len(alpha) - 1, 0) * qt,
                         node["name"])]
        for event_id, k, size in events:
            q_k = alpha[k - 1] / math.comb(size - 1, k - 1) * qt
            children.append(leaf(event_id, q_k, "CCF " + event_id))
        return gate("ccfgate:" + node["id"], "OR", children)

    return replace_leaves(tree, make)


def event_ids(result):
    return {event["id"] for cs in result["cutSets"] for event in cs["events"]}


def flatten(node, parent=None, out=None):
    out = [] if out is None else out
    out.append((node["id"], parent, node.get("logicGate") if node["children"] else None,
                node["probability"] if not node["children"] else None))
    for child in node["children"]:
        flatten(child, node["id"], out)
    return out


def load_generator():
    assert GENERATOR.is_file(), "the generator is missing: %s" % GENERATOR
    spec = importlib.util.spec_from_file_location("make_perf_fixtures_under_test", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# (i) the expansion technique against SPEC 7.4 (passes today)
# --------------------------------------------------------------------------


def tiny(kind):
    return gate("top", kind, [leaf("A", 1e-3), leaf("B", 1e-3)], type_="Root")


def ids_of(cut_set):
    return sorted(e["id"] for e in cut_set["events"])


def test_r1_and_of_two_with_beta_matches_the_spec_oracle():
    group = [{"id": "g1", "members": ["A", "B"]}]
    result = cutsets.compute(expand_beta(tiny("AND"), group, 0.1), SETTINGS, LIMITS)
    sets = {tuple(ids_of(cs)): cs for cs in result["cutSets"]}
    assert set(sets) == {("A", "B"), ("ccf:g1",)}
    assert sets[("A", "B")]["probability"] == pytest.approx(8.1e-7, rel=1e-12)
    assert sets[("ccf:g1",)]["probability"] == pytest.approx(1e-4, rel=1e-12)
    assert result["total"] == 2
    # one shared variable: the CCF id occurs once per cut set, and is repeated
    assert [e["id"] for e in sets[("ccf:g1",)]["events"]] == ["ccf:g1"]
    assert "ccf:g1" in {r["id"] for r in result["repeatedEvents"]}
    assert result["rareEvent"] == pytest.approx(1.0081e-4, rel=1e-12)  # R1
    assert result["mcub"] == pytest.approx(1.00809919e-4, rel=1e-9)  # R1h


def test_r2_or_of_two_with_beta_matches_the_spec_oracle():
    group = [{"id": "g1", "members": ["A", "B"]}]
    result = cutsets.compute(expand_beta(tiny("OR"), group, 0.1), SETTINGS, LIMITS)
    assert {tuple(ids_of(cs)) for cs in result["cutSets"]} == {("A",), ("B",), ("ccf:g1",)}
    assert result["rareEvent"] == pytest.approx(1.9e-3, rel=1e-12)  # R2
    assert result["mcub"] == pytest.approx(1.899010081e-3, rel=1e-9)  # R2h


def test_alpha_expansion_reproduces_the_beta_factor_for_two_members():
    """SPEC 7.3: staggered alpha with m = 2 and alpha_2 = beta equals the beta
    factor (R5 equals R1)."""
    group = [{"id": "g1", "members": ["A", "B"]}]
    result = cutsets.compute(
        expand_alpha_staggered(tiny("AND"), group, (0.9, 0.1)), SETTINGS, LIMITS)
    assert {tuple(ids_of(cs)) for cs in result["cutSets"]} == {("A", "B"), ("ccf:g1:A+B",)}
    assert result["rareEvent"] == pytest.approx(1.0081e-4, rel=1e-12)


# --------------------------------------------------------------------------
# (ii) the derived results for the two CCF fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def beta_expanded():
    members = [m for g in BETA_GROUPS for m in g["members"]]
    tree = expand_beta(base_tree(members), BETA_GROUPS, BETA)
    return cutsets.compute(tree, SETTINGS, LIMITS)


@pytest.fixture(scope="module")
def alpha_expanded():
    members = [m for g in ALPHA_GROUPS for m in g["members"]]
    tree = expand_alpha_staggered(base_tree(members), ALPHA_GROUPS, ALPHA)
    return cutsets.compute(tree, SETTINGS, LIMITS)


def test_the_derived_beta_tree_shares_one_variable_per_group(beta_expanded):
    ids = event_ids(beta_expanded)
    ccf_ids = {i for i in ids if i.startswith("ccf:")}
    assert ccf_ids == {"ccf:G%d" % k for k in range(1, 11)}
    for cs in beta_expanded["cutSets"]:
        listed = [e["id"] for e in cs["events"]]
        assert len(listed) == len(set(listed))
    repeated = {r["id"] for r in beta_expanded["repeatedEvents"]}
    assert {"ccf:G%d" % k for k in range(1, 11)} <= repeated


def test_every_beta_ccf_event_is_in_a_derived_cut_set(beta_expanded):
    ids = event_ids(beta_expanded)
    for k in range(1, 11):
        assert "ccf:G%d" % k in ids


def test_beta_derived_result_is_cut_by_order_and_not_by_time(beta_expanded):
    assert "order" in beta_expanded["truncatedBy"]
    assert "time" not in beta_expanded["truncatedBy"]
    assert beta_expanded["truncated"] is bool(beta_expanded["truncatedBy"])
    assert beta_expanded["truncatedBy"] == sorted(beta_expanded["truncatedBy"])
    assert beta_expanded["total"] == len(beta_expanded["cutSets"]) > 0


def test_every_alpha_ccf_event_is_in_a_derived_cut_set(alpha_expanded):
    expected = set()
    for g in ALPHA_GROUPS:
        for k in range(2, 5):
            for subset in itertools.combinations(g["members"], k):
                expected.add("ccf:%s:%s" % (g["id"], "+".join(subset)))
    assert len(expected) == 55
    assert expected <= event_ids(alpha_expanded)
    assert {i for i in event_ids(alpha_expanded) if i.startswith("ccf:")} == expected


def test_alpha_derived_result_is_not_cut_by_time(alpha_expanded):
    assert "time" not in alpha_expanded["truncatedBy"]
    assert alpha_expanded["truncated"] is bool(alpha_expanded["truncatedBy"])
    assert alpha_expanded["total"] == len(alpha_expanded["cutSets"]) > 0


# --------------------------------------------------------------------------
# the committed trees are the base tree; the constants are the derived values
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path, groups", [(CCF_FIXTURE, BETA_GROUPS),
                                          (ALPHA_FIXTURE, ALPHA_GROUPS)])
def test_the_committed_fixture_tree_is_the_spec_base_tree(path, groups):
    document = json.loads(path.read_text(encoding="utf-8"))
    members = [m for g in groups for m in g["members"]]
    expected = flatten(base_tree(members))
    actual = flatten(document["tree"])
    assert [row[:3] for row in actual] == [row[:3] for row in expected]
    for (nid, _, _, q_actual), (_, _, _, q_expected) in zip(actual, expected):
        if q_expected is not None:
            assert q_actual == pytest.approx(q_expected, rel=1e-12), nid


def test_generator_constant_ccf_cutset_count_is_the_derived_one(beta_expanded):
    constant = load_generator().EXPECTED_CCF_CUTSET_COUNT
    assert isinstance(constant, int) and not isinstance(constant, bool)
    assert constant == beta_expanded["total"]


def test_generator_constant_ccf_truncated_by_is_the_derived_one(beta_expanded):
    constant = load_generator().EXPECTED_CCF_TRUNCATED_BY
    assert isinstance(constant, list) and all(isinstance(s, str) for s in constant)
    assert constant == sorted(constant)
    assert constant == beta_expanded["truncatedBy"]


def test_generator_constant_alpha_cutset_count_is_the_derived_one(alpha_expanded):
    constant = load_generator().EXPECTED_ALPHA_CUTSET_COUNT
    assert isinstance(constant, int) and not isinstance(constant, bool)
    assert constant == alpha_expanded["total"]
