"""F2A BRIEF criterion 2 (FN-42): the staggered alpha model.

    Q_k = alpha_k / C(m-1, k-1) * Q_t          (S1 Eq. 5.6 p. 40)

Reference cases (SPEC 7.4, Q_t = 1e-3), copied into ``_alpha_models``:

====  ==============================  ==============================================
R5    m = 2, alpha (0.9, 0.1)         Q_2 = 1e-4, equal to R1 (exact)
R7    m = 3, alpha (0.955, 0.034,     CCF part 3 Q_2 + Q_3 = 6.2e-5 (exact)
      0.011) (S3 p. 7-16)
R8    same, 2-of-3                    7 cut sets; rare-event 6.4736075e-5 (exact)
R8h   same                            MCUB 6.47344749e-5 (rounded)
R10   same, 1-of-3 (all three fail)   Q_1^3 + 3 Q_1 Q_2 + Q_3 = 1.10495760e-5 (published
                                      formula, overlapping CCF events omitted)
R10h  same, as the editor computes    rare-event 1.10504430e-5 = R10 + 3 Q_2^2
====  ==============================  ==============================================

Tolerances as SPEC 7.4: relative 1e-12 (rare-event, "exact"), 1e-9 (MCUB), half a unit of the
last printed digit ("rounded"). The source errors of SPEC 7.3 are not used.
"""
import pytest

import _alpha_models as M

ST = "staggered"


def group3(**over):
    return M.agroup(members=["A", "B", "D"], alpha=M.ALPHA3, testing=ST, **over)


# ------------------------------------------------------------------ R5


def test_r5_pair_probability_equals_r1():
    independent, events = M.expansion(M.agroup(alpha=(0.9, 0.1), testing=ST))
    assert events[0][0] == (0, 1)
    assert events[0][1] == pytest.approx(M.R5_Q2, rel=M.REL12, abs=0.0)       # 1e-4
    assert independent[0] == pytest.approx(M.R5_Q1, rel=M.REL12, abs=0.0)     # 9e-4
    assert independent[1] == pytest.approx(M.R5_Q1, rel=M.REL12, abs=0.0)


def test_r5_and_of_two_gives_the_r1_numbers():
    result = M.compute(M.and_tree(["A", "B"]), [M.agroup(alpha=(0.9, 0.1), testing=ST)])
    assert sorted(M.cut_set_ids(result)) == [["A", "B"], ["ccf:g1:A+B"]]
    assert result["rareEvent"] == pytest.approx(M.R5_RARE, rel=M.REL12, abs=0.0)
    assert result["mcub"] == pytest.approx(M.R5_MCUB, rel=M.REL9, abs=0.0)
    assert M.find_cut_set(result, ["ccf:g1:A+B"])["probability"] == pytest.approx(1e-4, rel=M.REL12, abs=0.0)
    assert M.find_cut_set(result, ["A", "B"])["probability"] == pytest.approx(8.1e-7, rel=M.REL12, abs=0.0)


# ------------------------------------------------------------------ R7


def test_r7_probabilities_and_ccf_part():
    independent, events = M.expansion(group3())
    pairs = [q for idx, q in events if len(idx) == 2]
    triples = [q for idx, q in events if len(idx) == 3]
    assert len(pairs) == 3 and len(triples) == 1
    for q1 in independent:
        assert q1 == pytest.approx(M.R7_Q1, rel=M.REL12, abs=0.0)             # 9.55e-4
    for q2 in pairs:
        assert q2 == pytest.approx(M.R7_Q2, rel=M.REL12, abs=0.0)             # 1.7e-5 = 0.034 / 2 * 1e-3
    assert triples[0] == pytest.approx(M.R7_Q3, rel=M.REL12, abs=0.0)         # 1.1e-5 = 0.011 * 1e-3
    assert 3 * pairs[0] + triples[0] == pytest.approx(M.R7_CCF_PART, rel=M.REL12, abs=0.0)   # 6.2e-5


# ------------------------------------------------------------------ R8, R8h


def test_r8_two_of_three_has_exactly_seven_cut_sets_and_the_rare_event_sum():
    result = M.compute(M.kofn_tree(["A", "B", "D"], 2), [group3()])
    assert result["total"] == M.R8_CUTSETS == 7
    assert len(result["cutSets"]) == 7
    assert sorted(M.cut_set_ids(result)) == sorted([
        ["A", "B"], ["A", "D"], ["B", "D"],
        ["ccf:g1:A+B"], ["ccf:g1:A+D"], ["ccf:g1:B+D"], ["ccf:g1:A+B+D"]])
    assert result["rareEvent"] == pytest.approx(M.R8_RARE, rel=M.REL12, abs=0.0)   # 6.4736075e-5
    # 3 Q_1^2 + 3 Q_2 + Q_3 term by term
    assert result["rareEvent"] == pytest.approx(
        3 * M.R7_Q1 ** 2 + 3 * M.R7_Q2 + M.R7_Q3, rel=M.REL12, abs=0.0)


def test_r8h_two_of_three_min_cut_upper_bound():
    result = M.compute(M.kofn_tree(["A", "B", "D"], 2), [group3()])
    assert M.near(result["mcub"], *M.R8H_MCUB), result["mcub"]            # 6.47344749e-5


# ------------------------------------------------------------------ R10, R10h


def test_r10h_one_of_three_keeps_the_overlapping_ccf_events():
    result = M.compute(M.and_tree(["A", "B", "D"]), [group3()])
    # 1 + 3 (pair event with the third independent part) + 3 (two pair events) + 1 (triple) = 8
    assert result["total"] == 8
    assert M.near(result["rareEvent"], *M.R10H_RARE), result["rareEvent"]  # 1.10504430e-5
    overlap = M.find_cut_set(result, ["ccf:g1:A+B", "ccf:g1:A+D"])         # {C_AB, C_AC}
    assert overlap["probability"] == pytest.approx(M.R7_Q2 ** 2, rel=M.REL12, abs=0.0)
    assert {"ccf:g1:A+B", "ccf:g1:A+D"} <= {e["id"] for e in overlap["events"]}
    # the triple event is not absorbed by the pair-pair sets, nor the reverse
    M.find_cut_set(result, ["ccf:g1:A+B+D"])


def test_r10h_minus_r10_is_three_q2_squared():
    result = M.compute(M.and_tree(["A", "B", "D"]), [group3()])
    q1, q2, q3 = M.R7_Q1, M.R7_Q2, M.R7_Q3
    r10 = q1 ** 3 + 3 * q1 * q2 + q3                                       # published formula
    assert M.near(r10, *M.R10_PUBLISHED), r10                              # 1.10495760e-5
    assert result["rareEvent"] - r10 == pytest.approx(3 * q2 ** 2, rel=1e-9, abs=0.0)   # 8.67e-10


# ------------------------------------------------------------------ system level, m = 4
# S1 Tables 5-4 and 5-5 have the m = 4 rows swapped (SPEC 7.3: source error not to copy), so the
# m = 4 system results are derived here from Eq. 5.6 and the Case formulas of S1 Table 5-2 p. 49
# (Case 8 and Case 9), never from Table 5-4. Group of four independent basic events,
# staggered, alpha (0.95, 0.03, 0.01, 0.01), Q_t = 1e-3 (DESIGN 8 (b)):
#   Q_1 = 0.95e-3 = 9.5e-4,  Q_2 = 0.03/3 * 1e-3 = 1e-5,  Q_3 = 0.01/3 * 1e-3 = 3.3333333e-6,
#   Q_4 = 0.01 * 1e-3 = 1e-5   (C(3,k-1) = 1, 3, 3, 1).


def test_m4_four_of_four_must_operate_is_the_or_of_the_members():
    """S1 Table 5-2 Case 9 p. 49: 4 Q_1 + 6 Q_2 + 4 Q_3 + Q_4. In exact fractions:
    4 * 19/20000 + 6 * 1/100000 + 4 * 1/300000 + 1/100000 = 233/60000 = 3.88333333...e-3."""
    members = M.IDS[:4]
    result = M.compute(M.or_tree(members), [M.agroup(members=members, alpha=M.PERF_ALPHA, testing=ST)])
    assert result["total"] == 15 == 4 + 6 + 4 + 1          # every event is a cut set of its own
    assert M.near(result["rareEvent"], 3.8833333e-3, 5e-11), result["rareEvent"]
    q = M.PERF_Q[ST]
    assert result["rareEvent"] == pytest.approx(4 * q[0] + 6 * q[1] + 4 * q[2] + q[3], rel=M.REL12, abs=0.0)


def test_m4_three_of_four_must_operate_is_the_two_of_four_gate():
    """S1 Table 5-2 Case 8 p. 49: 6 Q_1^2 + 6 Q_2 + 4 Q_3 + Q_4. In exact fractions:
    6 * (19/20000)^2 + 6/100000 + 4/300000 + 1/100000 = 8.87483333...e-5. The CCF term is
    6 Q_2 + 4 Q_3 + Q_4 = 8.3333333e-5; copying the swapped Table 5-4 row ("3/4 of 4" holds
    4 Q_3 + Q_4) would give a CCF term of 2.33e-5 instead."""
    members = M.IDS[:4]
    result = M.compute(M.kofn_tree(members, 2),
                       [M.agroup(members=members, alpha=M.PERF_ALPHA, testing=ST)])
    assert result["total"] == 17 == 6 + 6 + 4 + 1          # 6 pairs of parts, 6 + 4 + 1 events
    assert M.near(result["rareEvent"], 8.8748333e-5, 5e-13), result["rareEvent"]
    q = M.PERF_Q[ST]
    assert result["rareEvent"] == pytest.approx(
        6 * q[0] ** 2 + 6 * q[1] + 4 * q[2] + q[3], rel=M.REL12, abs=0.0)
    ccf_term = sum(cs["probability"] for cs in result["cutSets"]
                   if any(e["id"].startswith("ccf:") for e in cs["events"]))
    assert M.near(ccf_term, 8.3333333e-5, 5e-13), ccf_term     # not 2.33e-5


# ------------------------------------------------------------------ m = 2 equals beta
# A derivation from Eq. 5.6 (k = 1, 2); S1 p. E-2 states the three-component relation only.


def normalised(result):
    """{sorted tuple of event ids with every CCF id shortened to 'ccf'}: probability, without
    the sets of probability zero."""
    out = {}
    for cs in result["cutSets"]:
        if cs["probability"] == 0:
            continue
        key = tuple(sorted("ccf" if e["id"].startswith("ccf:") else e["id"] for e in cs["events"]))
        out[key] = cs["probability"]
    return out


@pytest.mark.parametrize("beta", [0, 0.05, 0.1, 1])
@pytest.mark.parametrize("shape", ["and", "or"])
def test_m_equals_2_with_alpha_one_minus_beta_and_beta_is_the_beta_model(beta, shape):
    tree = M.and_tree(["A", "B"]) if shape == "and" else M.or_tree(["A", "B"])
    alpha = (1.0 - beta, float(beta))
    alpha_result = M.compute(tree, [M.agroup(alpha=alpha, testing=ST)])
    beta_result = M.compute(tree, [M.bgroup(beta=beta)])
    assert [g["id"] for g in alpha_result["ccf"]["applied"]] == ["g1"]   # the alpha group is applied
    # the pair event reaches the cut sets, except for beta = 0 where its q = 0 drops out (F2 R3)
    has_pair = any(e["id"] == "ccf:g1:A+B" for cs in alpha_result["cutSets"] for e in cs["events"])
    assert has_pair or beta == 0
    a, b = normalised(alpha_result), normalised(beta_result)
    assert a.keys() == b.keys(), (a, b)
    for key in a:
        assert a[key] == pytest.approx(b[key], rel=1e-12, abs=0.0), key
    assert alpha_result["rareEvent"] == pytest.approx(beta_result["rareEvent"], rel=1e-12, abs=0.0)
    assert alpha_result["mcub"] == pytest.approx(beta_result["mcub"], rel=1e-12, abs=0.0)


def test_the_alpha_event_id_of_a_pair_is_the_member_pair_and_the_beta_id_is_unchanged():
    """A beta file still reproduces F2: id ``ccf:<groupId>``, R1 numbers."""
    beta_result = M.compute(M.and_tree(["A", "B"]), [M.bgroup(beta=0.1)])
    assert sorted(M.cut_set_ids(beta_result)) == [["A", "B"], ["ccf:g1"]]
    assert beta_result["rareEvent"] == pytest.approx(M.R5_RARE, rel=M.REL12, abs=0.0)   # R1: 1.0081e-4
    assert beta_result["mcub"] == pytest.approx(M.R5_MCUB, rel=M.REL9, abs=0.0)
    alpha_result = M.compute(M.and_tree(["A", "B"]), [M.agroup(alpha=(0.9, 0.1), testing=ST)])
    assert sorted(M.cut_set_ids(alpha_result)) == [["A", "B"], ["ccf:g1:A+B"]]


# ------------------------------------------------------------------ normalisation (FN-43)


def test_staggered_normalisation_divides_each_alpha_by_the_sum():
    """Only the staggered formula shows it numerically: the un-normalised Q_1 would be
    0.9555e-3 and is not used; Q_1 = 0.9555 / 1.0005 * 1e-3."""
    alpha = (0.9555, 0.034, 0.011)
    independent, events = M.expansion(M.agroup(members=["A", "B", "D"], alpha=alpha, testing=ST))
    total = 0.9555 + 0.034 + 0.011
    assert independent[0] == pytest.approx(0.9555 / total * 1e-3, rel=M.REL12, abs=0.0)
    assert independent[0] != pytest.approx(0.9555e-3, rel=1e-6, abs=0.0)
    pair = [q for idx, q in events if len(idx) == 2][0]
    assert pair == pytest.approx(0.034 / total / 2 * 1e-3, rel=M.REL12, abs=0.0)
    # the hand-divided set gives the same events
    by_hand = tuple(a / total for a in alpha)
    other = M.expansion(M.agroup(members=["A", "B", "D"], alpha=by_hand, testing=ST))
    assert other[0] == pytest.approx(independent, rel=M.REL12, abs=0.0)


def test_a_sum_inside_1e_9_is_divided_by_the_sum_and_raises_no_warning(api):
    """DESIGN A4 / O8: a sum within 1e-9 is divided by its sum all the same (no warning). The sum
    here is 1 + 5e-10, so dividing shifts Q_1 by 5e-10 relative: visible at rel 1e-12 / 1e-11,
    invisible at the earlier 1e-8."""
    alpha = (0.955, 0.034, 0.011 + 5e-10)
    total = 0.955 + 0.034 + (0.011 + 5e-10)
    assert 1e-10 < abs(total - 1.0) < 1e-9
    independent, events = M.expansion(M.agroup(members=["A", "B", "D"], alpha=alpha, testing=ST))
    # S1 Eq. 5.6 with alpha_1 / sum: the divided value, at relative 1e-12
    assert independent[0] == pytest.approx(0.955 / total * 1e-3, rel=1e-12, abs=0.0)
    # and it is NOT the undivided 0.955 * Q_t (the true shift is 5e-10 relative)
    assert independent[0] != pytest.approx(0.955e-3, rel=1e-11, abs=0.0)
    pair = [q for idx, q in events if len(idx) == 2][0]
    assert pair == pytest.approx(0.034 / total / 2 * 1e-3, rel=1e-12, abs=0.0)
    assert pair != pytest.approx(0.034 / 2 * 1e-3, rel=1e-11, abs=0.0)
    # ... and no CCF_ALPHA_NORMALISED warning (it appears only above 1e-9)
    api.open_doc(M.document(M.and_tree(["A", "B", "D"]), [
        M.agroup(members=["A", "B", "D"], alpha=alpha, testing=ST)]))
    (group,) = api.groups()["groups"]
    assert group["status"]["applied"] is True and group["status"]["warnings"] == []


# ------------------------------------------------------------------ S1 Table 6-9 p. 104


@pytest.mark.parametrize("name, alpha, values_sum", M.TABLE_6_9, ids=[t[0] for t in M.TABLE_6_9])
def test_table_6_9_set_is_applied_with_the_staggered_oracles(api, name, alpha, values_sum):
    members = ["A", "B", "C", "D"]
    group = M.agroup(members=members, alpha=alpha, testing=ST)
    expected = M.TABLE_6_9_Q[(name, ST)]
    independent, events = M.expansion(group)
    for q1 in independent:
        assert q1 == pytest.approx(expected[0], rel=M.REL12, abs=0.0)
    for idx, q in events:
        assert q == pytest.approx(expected[len(idx) - 1], rel=M.REL12, abs=0.0), idx
    qs = M.event_q(M.or_tree(members), [group])
    assert qs["A"] == pytest.approx(expected[0], rel=M.REL12, abs=0.0)
    for idx in M.subsets(4):
        assert qs[M.subset_id("g1", members, idx)] == pytest.approx(
            expected[len(idx) - 1], rel=M.REL12, abs=0.0)
    api.open_doc(M.document(M.or_tree(members), [group]))
    (listed,) = api.groups()["groups"]
    assert listed["status"]["applied"] is True
    (warning,) = listed["status"]["warnings"]
    assert warning["code"] == "CCF_ALPHA_NORMALISED" and values_sum in warning["reason"]["en"]
    # the normalisation happened: Q_1 is alpha_1 / sum * Q_t, not alpha_1 * Q_t
    assert expected[0] != pytest.approx(alpha[0] * 1e-3, rel=1e-6, abs=0.0)


def test_the_perf_alpha_set_staggered_oracles():
    members = M.IDS[:4]
    group = M.agroup(members=members, alpha=M.PERF_ALPHA, testing=ST)
    expected = M.PERF_Q[ST]
    independent, events = M.expansion(group)
    assert independent[0] == pytest.approx(expected[0], rel=M.REL12, abs=0.0)
    for idx, q in events:
        assert q == pytest.approx(expected[len(idx) - 1], rel=M.REL12, abs=0.0)
    assert len(events) == 11
