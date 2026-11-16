"""F2A BRIEF criterion 1 (FN-41): the non-staggered alpha model.

    Q_k = k / C(m-1, k-1) * (alpha_k / alpha_t) * Q_t,   alpha_t = sum k * alpha_k
    (S1 Eq. 5.7-5.9 p. 41; S2 Eq. C.23-C.24 pp. C-10/C-11)

One CCF event per member subset of size k >= 2 (q = Q_k, id ``ccf:<groupId>:<m1>+<m2>...``,
members in group order); each member = OR(independent part with Q_1, every CCF event that
contains it). Reference cases (SPEC 7.4, Q_t = 1e-3), copied into ``_alpha_models``:

====  =====================================  ===========================================
R6    m = 2, alpha (0.95, 0.05)              Q_2 = 9.5238095e-5 (rounded)
R6h   same, AND of 2                         Q_1 = 9.0476190e-4; rare-event 9.6056689e-5;
                                             MCUB 9.6056611e-5 (rounded)
R9    m = 3, alpha (0.955, 0.034, 0.011)     CCF part 1.27841e-4 (rounded), alpha_t = 1.056
R9h   same, 2-of-3                           rare-event 1.302945e-4; MCUB 1.302880e-4
====  =====================================  ===========================================

"rounded" = half a unit of the last printed digit. The source errors of SPEC 7.3 are not used.
"""
import math

import pytest

import _alpha_models as M

ND = "nonStaggered"


def group3(**over):
    return M.agroup(members=["A", "B", "D"], alpha=M.ALPHA3, testing=ND, **over)


# ------------------------------------------------------------------ R6, R6h


def test_r6_pair_probability_and_independent_part():
    independent, events = M.expansion(M.agroup(alpha=(0.95, 0.05), testing=ND))
    assert len(independent) == 2
    assert events and len(events) == 1 and events[0][0] == (0, 1)
    q2 = events[0][1]
    assert M.near(q2, *M.R6_Q2), q2                         # 9.5238095e-5
    for q1 in independent:
        assert M.near(q1, *M.R6H_Q1), q1                    # 9.0476190e-4
    expected = M.oracle_q(2, (0.95, 0.05), ND)
    assert q2 == pytest.approx(expected[1], rel=M.REL12, abs=0.0)
    assert independent[0] == pytest.approx(expected[0], rel=M.REL12, abs=0.0)


def test_r6h_and_of_two_rare_event_sum_and_mcub():
    group = M.agroup(alpha=(0.95, 0.05), testing=ND)
    result = M.compute(M.and_tree(["A", "B"]), [group])
    assert sorted(M.cut_set_ids(result)) == [["A", "B"], ["ccf:g1:A+B"]]
    assert M.near(result["rareEvent"], *M.R6H_RARE), result["rareEvent"]   # 9.6056689e-5
    assert M.near(result["mcub"], *M.R6H_MCUB), result["mcub"]             # 9.6056611e-5
    ccf_set = M.find_cut_set(result, ["ccf:g1:A+B"])
    assert M.near(ccf_set["probability"], *M.R6_Q2)
    both = M.find_cut_set(result, ["A", "B"])
    assert both["probability"] == pytest.approx(M.R6H_Q1[0] ** 2, rel=1e-6, abs=0.0)
    # the rare-event sum is Q_1^2 + Q_2 from the formulas (relative 1e-12 against the oracle)
    q1, q2 = M.oracle_q(2, (0.95, 0.05), ND)
    assert result["rareEvent"] == pytest.approx(q1 * q1 + q2, rel=M.REL12, abs=0.0)
    # MCUB = 1 - (1 - Q_2)(1 - Q_1^2)
    assert result["mcub"] == pytest.approx(1 - (1 - q2) * (1 - q1 * q1), rel=M.REL9, abs=0.0)


# ------------------------------------------------------------------ R9, R9h


def test_r9_triple_group_probabilities():
    independent, events = M.expansion(group3())
    q1 = independent[0]
    pairs = [q for idx, q in events if len(idx) == 2]
    triples = [q for idx, q in events if len(idx) == 3]
    assert independent == (q1, q1, q1)
    assert len(pairs) == 3 and len(triples) == 1
    assert M.near(q1, *M.R9_Q1), q1                         # 9.0435606e-4
    for q2 in pairs:
        assert M.near(q2, *M.R9_Q2), q2                     # 3.2196970e-5
    assert M.near(triples[0], *M.R9_Q3), triples[0]         # 3.1250000e-5
    # alpha_t = 1 * 0.955 + 2 * 0.034 + 3 * 0.011 = 1.056 (SPEC 7.4 R9)
    alpha_t = sum((k + 1) * a for k, a in enumerate(M.ALPHA3))
    assert alpha_t == pytest.approx(M.R9_ALPHA_T, rel=1e-12, abs=0.0)
    expected = M.oracle_q(3, M.ALPHA3, ND)
    assert pairs[0] == pytest.approx(expected[1], rel=M.REL12, abs=0.0)
    assert triples[0] == pytest.approx(expected[2], rel=M.REL12, abs=0.0)
    assert q1 == pytest.approx(expected[0], rel=M.REL12, abs=0.0)


def test_r9_ccf_part_of_a_member():
    """CCF part 3 Q_2 + Q_3 = 1.27841e-4 (rounded)."""
    _independent, events = M.expansion(group3())
    ccf_part = sum(q for idx, q in events if len(idx) == 2) + sum(
        q for idx, q in events if len(idx) == 3)
    assert M.near(ccf_part, *M.R9_CCF_PART), ccf_part


def test_r9h_two_of_three_rare_event_sum_and_mcub():
    result = M.compute(M.kofn_tree(["A", "B", "D"], 2), [group3()])
    assert result["total"] == M.R8_CUTSETS == 7
    assert M.near(result["rareEvent"], *M.R9H_RARE), result["rareEvent"]   # 1.302945e-4
    assert M.near(result["mcub"], *M.R9H_MCUB), result["mcub"]             # 1.302880e-4
    # the 4 CCF events are one cut set each, the pairs of independent parts the other 3
    ids = sorted(M.cut_set_ids(result))
    assert ids == sorted([
        ["A", "B"], ["A", "D"], ["B", "D"], ["ccf:g1:A+B"], ["ccf:g1:A+D"], ["ccf:g1:B+D"],
        ["ccf:g1:A+B+D"]])


# ------------------------------------------------------------------ ids, order, shape


@pytest.mark.parametrize("m, count", [(2, 1), (3, 4), (4, 11)])
def test_one_event_per_subset_of_two_or_more_in_group_order(m, count):
    members = M.IDS[:m]
    alpha = (0.7, 0.2, 0.06, 0.04)[:m]
    alpha = tuple(a / sum(alpha) for a in alpha)
    group = M.agroup(members=members, alpha=alpha, testing=ND)
    independent, events = M.expansion(group)
    assert len(independent) == m
    assert len(events) == count == 2 ** m - m - 1
    # order: by size ascending, then lexicographic in group positions
    assert [idx for idx, _q in events] == M.subsets(m)
    expected = M.oracle_q(m, alpha, ND)
    for idx, q in events:
        assert q == pytest.approx(expected[len(idx) - 1], rel=M.REL12, abs=0.0), idx
    for q1 in independent:
        assert q1 == pytest.approx(expected[0], rel=M.REL12, abs=0.0)

    s = M.compiled(M.or_tree(members), [group])
    ids = [e["id"] for e in s.events if e["id"].startswith("ccf:")]
    assert ids == [M.subset_id("g1", members, idx) for idx in M.subsets(m)]
    assert len(ids) == len(set(ids)) == count


def test_the_events_of_a_group_of_three_in_the_documented_order():
    s = M.compiled(M.or_tree(["A", "B", "D"]), [group3()])
    ids = [e["id"] for e in s.events if e["id"].startswith("ccf:")]
    assert ids == ["ccf:g1:A+B", "ccf:g1:A+D", "ccf:g1:B+D", "ccf:g1:A+B+D"]
    order = [e["id"] for e in s.events]
    # the independent part of the first member comes first; every CCF event of the group is
    # created at that first reference, before the second member's independent part (DESIGN 3.3)
    assert order[0] == "A"
    assert max(order.index(i) for i in ids) < order.index("B")


def test_event_names_markers_and_independent_part_values():
    s = M.compiled(M.or_tree(["A", "B", "D"]), [group3()])
    by_id = {e["id"]: e for e in s.events}
    expected = M.oracle_q(3, M.ALPHA3, ND)
    assert by_id["A"]["q"] == pytest.approx(expected[0], rel=M.REL12, abs=0.0)       # Q_1
    assert by_id["A"]["derived"]["q"] == pytest.approx(M.QT, rel=M.REL12, abs=0.0)   # Q_t is kept
    assert by_id["A"]["name"] == "Pump A (independent part)"
    pair = by_id["ccf:g1:A+D"]
    assert pair["q"] == pytest.approx(expected[1], rel=M.REL12, abs=0.0)
    assert pair["name"] == "CCF: Relief valves (Pump A + Pump D)"
    assert pair["ccf"]["groupId"] == "g1" and pair["ccf"]["role"] == "event"
    assert pair["ccf"]["members"] == ["A", "D"]
    assert pair["ccf"]["memberNames"] == ["Pump A", "Pump D"]       # DESIGN 3.3 (alpha events only)
    assert pair["ccf"]["baseName"] == M.GROUP_NAME
    assert pair["quant"] is None
    triple = by_id["ccf:g1:A+B+D"]
    assert triple["q"] == pytest.approx(expected[2], rel=M.REL12, abs=0.0)
    assert triple["name"] == "CCF: Relief valves (Pump A + Pump B + Pump D)"
    assert triple["ccf"]["members"] == ["A", "B", "D"]
    assert triple["ccf"]["memberNames"] == ["Pump A", "Pump B", "Pump D"]


def test_each_member_is_the_or_of_its_independent_part_and_every_event_containing_it():
    """AND of A and B with a group {A, B, D}: A = OR(A', AB, AD, ABD), B = OR(B', AB, BD, ABD)
    gives the minimal cut sets {AB}, {ABD}, {A', B'}, {A', BD}, {AD, B'}, {AD, BD}. Pair events
    that contain D appear, the ones that do not contain A or B do not. D sits under an AND with
    a zero-probability leaf, so it adds no cut set of its own."""
    tree = M.top([M.gate("G1", "AND", [M.pump("A"), M.pump("B")], name="Pumps fail"),
                  M.gate("G2", "AND", [M.pump("D"), M.leaf("Z", 0.0)], name="Unused")])
    result = M.compute(tree, [group3()])
    ids = sorted(M.cut_set_ids(result))
    want = sorted([
        ["ccf:g1:A+B"], ["ccf:g1:A+B+D"], ["A", "B"], ["A", "ccf:g1:B+D"],
        ["B", "ccf:g1:A+D"], ["ccf:g1:A+D", "ccf:g1:B+D"]])
    assert ids == want


def test_or_of_all_members_has_every_event_as_a_single_cut_set():
    members = ["A", "B", "D"]
    result = M.compute(M.or_tree(members), [group3()])
    assert result["total"] == 3 + 4
    qs = M.oracle_q(3, M.ALPHA3, ND)
    # rare-event sum = sum_k C(m,k) Q_k
    assert result["rareEvent"] == pytest.approx(
        sum(math.comb(3, k) * qs[k - 1] for k in (1, 2, 3)), rel=M.REL12, abs=0.0)


def test_four_members_give_fifteen_events_in_an_or_tree():
    members = M.IDS[:4]
    alpha = (0.9, 0.06, 0.03, 0.01)
    result = M.compute(M.or_tree(members), [M.agroup(members=members, alpha=alpha, testing=ND)])
    assert result["total"] == 4 + 11


def test_the_operators_are_in_topological_order():
    from fta_web import logic

    s = M.compiled(M.kofn_tree(["A", "B", "D"], 2), [group3()])
    assert len([e for e in s.events if e["id"].startswith("ccf:")]) == 4
    for index, op in enumerate(s.ops):
        assert all(child < index for child in logic.op_children(op)), (index, op)


def test_a_member_linked_under_two_gates_gives_each_ccf_id_exactly_once():
    members = ["A", "B", "C"]
    group = M.agroup(members=members, alpha=M.ALPHA3, testing=ND)
    s = M.compiled(M.linked_tree(members), [group])
    ids = [e["id"] for e in s.events if e["id"].startswith("ccf:")]
    assert ids == [M.subset_id("g1", members, idx) for idx in M.subsets(3)]
    result = M.compute(M.linked_tree(members), [group])
    found = {e["id"] for cs in result["cutSets"] for e in cs["events"] if e["id"].startswith("ccf:")}
    assert found <= set(ids)
    assert {r["id"] for r in result["repeatedEvents"]} >= {"A", "ccf:g1:A+B"}


# ------------------------------------------------------------------ normalisation


def test_r9_with_an_alpha_sum_of_1_0005_equals_the_hand_divided_set():
    """FN-43: each alpha is divided by the sum. Non-staggered Q_k depends on alpha_k / alpha_t,
    so a constant factor changes nothing: both give the R9 numbers."""
    alpha = (0.9555, 0.034, 0.011)
    assert sum(alpha) == pytest.approx(1.0005, rel=1e-12, abs=0.0)
    total = sum(alpha)
    by_hand = tuple(a / total for a in alpha)
    one = M.expansion(M.agroup(members=["A", "B", "D"], alpha=alpha, testing=ND))
    two = M.expansion(M.agroup(members=["A", "B", "D"], alpha=by_hand, testing=ND))
    assert one[0] == pytest.approx(two[0], rel=M.REL12, abs=0.0)
    assert [q for _i, q in one[1]] == pytest.approx([q for _i, q in two[1]], rel=M.REL12, abs=0.0)
    expected = M.oracle_q(3, alpha, ND)
    assert one[0][0] == pytest.approx(expected[0], rel=M.REL12, abs=0.0)


def test_the_normalised_group_is_applied_and_reports_the_original_sum(api):
    alpha = [0.9555, 0.034, 0.011]
    api.open_doc(M.document(M.and_tree(["A", "B", "D"]), [
        M.agroup(members=["A", "B", "D"], alpha=alpha, testing=ND)]))
    (group,) = api.groups()["groups"]
    assert group["status"]["applied"] is True
    (warning,) = group["status"]["warnings"]
    assert warning["code"] == "CCF_ALPHA_NORMALISED"
    assert "1.0005" in warning["reason"]["en"] and "1.0005" in warning["message"]["en"]


# ------------------------------------------------------------------ S1 Table 6-9 p. 104


@pytest.mark.parametrize("name, alpha, values_sum", M.TABLE_6_9, ids=[t[0] for t in M.TABLE_6_9])
def test_table_6_9_set_is_applied_with_the_non_staggered_oracles(api, name, alpha, values_sum):
    members = ["A", "B", "C", "D"]
    group = M.agroup(members=members, alpha=alpha, testing=ND)
    expected = M.TABLE_6_9_Q[(name, ND)]
    independent, events = M.expansion(group)
    for q1 in independent:
        assert q1 == pytest.approx(expected[0], rel=M.REL12, abs=0.0)
    for idx, q in events:
        assert q == pytest.approx(expected[len(idx) - 1], rel=M.REL12, abs=0.0), idx
    # the same through the structure
    qs = M.event_q(M.or_tree(members), [group])
    assert qs["A"] == pytest.approx(expected[0], rel=M.REL12, abs=0.0)
    for idx in M.subsets(4):
        assert qs[M.subset_id("g1", members, idx)] == pytest.approx(
            expected[len(idx) - 1], rel=M.REL12, abs=0.0)
    # applied, with the warning that carries the sum of the printed values (S1 prints no sum)
    api.open_doc(M.document(M.or_tree(members), [group]))
    (listed,) = api.groups()["groups"]
    assert listed["status"]["applied"] is True
    (warning,) = listed["status"]["warnings"]
    assert warning["code"] == "CCF_ALPHA_NORMALISED"
    assert values_sum in warning["reason"]["en"]
    # all 15 events reach the cut sets
    result = M.compute(M.or_tree(members), [group])
    assert result["total"] == 4 + 11


def test_the_perf_alpha_set_non_staggered_oracles():
    members = M.IDS[:4]
    group = M.agroup(members=members, alpha=M.PERF_ALPHA, testing=ND)
    expected = M.PERF_Q[ND]
    independent, events = M.expansion(group)
    assert independent[0] == pytest.approx(expected[0], rel=M.REL12, abs=0.0)
    for idx, q in events:
        assert q == pytest.approx(expected[len(idx) - 1], rel=M.REL12, abs=0.0)
    total = independent[0] + sum(q for idx, q in events if 0 in idx)
    assert total == pytest.approx(M.QT, rel=M.REL12, abs=0.0)  # Sum C(3,k-1) Q_k = Q_t
