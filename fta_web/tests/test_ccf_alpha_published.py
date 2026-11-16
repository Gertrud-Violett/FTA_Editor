"""F2A: the tool against published numbers (NUREG/CR-5485 Chapter 6 example, MOV group).

Source S1 = NUREG/CR-5485 (Mosleh et al., 1998). Printed page = PDF page - 16.

The example (S1 Sections 6.3 and 6.4, pp. 91-105; Table 6-10 is in Section 6.4): a group of four motor-operated valves (MOV), failure
to open, staggered testing, Q_t = q_V = 4.30E-3 (Table 6-8 p. 103). The auxiliary feedwater
system fails (through the valves) when THREE of the four valves fail: its first order cut sets
are the global event V4 and the four triple events (Figure 6-6 p. 96), and its third order
independent cut sets are the four triples of independent valve failures, 4 V1^3 (S1 p. 95).
In S1's own wording that is a "2 of 4" success system (two valves must open); in this editor it
is a 3-of-4 failure gate (a K-out-of-N gate, k = 3, over the four valves).

The alpha values are the alpha values as printed in NUREG/CR-5485 Table 6-9 p. 104 (read by
one reader; the table prints no sum) - the plant-specific column (the same values are in Table
6-8 p. 103): (0.9668498, 1.47E-2, 1.16E-2, 6.86E-3). Their sum is 1.0000098, not 1, so this
tool divides every alpha by the sum (FN-43) and raises the NORMALISED warning; the published
terms rest on the unrounded alpha values of the CCF software, which the table does not print.

Published terms of the valve group (Table 6-10 p. 105; inputs Tables 6-8 p. 103 and 6-9 p. 104;
formulas Table 6-5 p. 97, staggered, Q_k = alpha_k / C(m-1, k-1) * Q_t with C(3, k-1) = 1, 3, 3, 1):

    V4        2.9E-5   the global event                      (alpha_4 Q_t)
    4 V3      6.6E-5   four triple events                    (4 alpha_3 / 3 Q_t)   NOT asserted, see below
    12 V2 V1  1.1E-6   pair event x independent event       (12 cut sets)
    4 V1^3    2.9E-7   independent triples                   (4 cut sets)

Each published number is checked within half a unit of its last printed digit (two significant
digits), as a purely relative tolerance (``abs=0.0``).

``4 V3`` is not asserted: the tool gives 6.6506E-5 where the table prints 6.6E-5, which allows
6.55E-5 to 6.65E-5. The difference (6E-9 absolute, 9E-5 relative) comes from the three-digit
alpha_3 = 1.16E-2 of Table 6-8 (q_v = 4.30E-3 has three digits as well); an unrounded alpha_3 from
0.01155 to 0.011599 (0.0115988) prints as 1.16E-2 and gives a printed 6.6E-5 (at 0.0115994 the
term is 6.6503E-5, which prints 6.7E-5). The structure (four triple events, one cut set each) and the formula
are checked instead.

Cases 2 and 3 (S1 Table 3-1 p. 13, global factor g for 4 members, staggered 0.04 / 0.08 and
non-staggered 0.11 / 0.19 for "2 of 4" / "3 of 4" success) are DOCUMENTED values at the end of
the file: published rounding not reproducible: S1 Table 3-1 rounds coarsely (the printed g are the
tool values rounded up to two decimals; S1 states no rule); tool value shown, no match claimed.
"""
import math

import pytest

from fta_web import ccf, cutsets

ALPHA_TABLE_6_9 = (0.9668498, 1.47e-2, 1.16e-2, 6.86e-3)   # plant-specific column, p. 104
QT = 4.30e-3                                                # Table 6-8 p. 103
MEMBERS = ["V1", "V2", "V3", "V4"]
SUM = math.fsum(ALPHA_TABLE_6_9)                            # 1.0000098


def published(value, digits):
    """``value`` printed with ``digits`` significant digits: half a unit of the last digit."""
    exponent = math.floor(math.log10(abs(value)))
    half = 0.5 * 10.0 ** (exponent - (digits - 1))
    return pytest.approx(value, rel=half / abs(value), abs=0.0)


def valve(node_id):
    return {"id": node_id, "name": "MOV " + node_id, "type": "Event", "logicGate": "OR",
            "probability": QT, "notes": "", "links": [], "children": [],
            "quant": {"model": "fixed"}}


def tree():
    """Top event OR [ 3-of-4 gate over the four valves ]: fails when three valves fail."""
    gate = {"id": "G1", "name": "Three of four valves fail", "type": "Event",
            "probability": 1.0, "notes": "", "links": [], "gateType": "KOFN", "logicGate": "OR",
            "k": 3, "children": [valve(i) for i in MEMBERS]}
    return {"id": "root", "name": "Top event", "type": "Root", "logicGate": "OR",
            "probability": 1.0, "notes": "", "links": [], "children": [gate]}


def group():
    return {"id": "g1", "name": "MOV group", "model": "alpha", "beta": None,
            "alpha": list(ALPHA_TABLE_6_9), "testing": "staggered", "members": list(MEMBERS),
            "source": "NUREG/CR-5485 Table 6-9 p. 104"}


@pytest.fixture(scope="module")
def result():
    return cutsets.compute(tree(), {"ccfGroups": [group()]}, {"timeBudgetS": 120})


def ccf_size(event_id):
    """Members failed by a CCF event id ``ccf:g1:V1+V2``; 0 for an independent event."""
    if not event_id.startswith("ccf:"):
        return 0
    return len(event_id.split(":")[2].split("+"))


def by_type(result):
    """{sorted tuple of event sizes (0 = independent): [cut sets]}."""
    out = {}
    for cut_set in result["cutSets"]:
        key = tuple(sorted(ccf_size(e["id"]) for e in cut_set["events"]))
        out.setdefault(key, []).append(cut_set)
    return out


def total(cut_sets):
    return math.fsum(cs["probability"] for cs in cut_sets)


def test_the_alpha_set_sums_to_1_0000098_and_is_normalised_with_a_warning():
    assert SUM == pytest.approx(1.0000098, rel=1e-12, abs=0.0)
    (assessment,) = ccf.assess([group()], tree(), {"ccfGroups": [group()]}, "FTA")
    assert assessment.applied
    codes = [f.code for f in assessment.findings]
    assert codes == ["CCF_ALPHA_NORMALISED"]
    # each alpha is divided by the sum: Q_1 = alpha_1 / 1.0000098 * Q_t
    expansion = ccf.event_probabilities("alpha", group(), [QT] * 4)
    assert expansion.independent[0] == pytest.approx(
        ALPHA_TABLE_6_9[0] / SUM * QT, rel=1e-12, abs=0.0)
    assert expansion.independent[0] != pytest.approx(ALPHA_TABLE_6_9[0] * QT, rel=1e-8, abs=0.0)


def test_cut_sets_grouped_by_type(result):
    groups = by_type(result)
    # the four triples of independent failures, the four triple events, the global event,
    # the 12 pair x independent products (S1 Figure 6-6 p. 96 lists the same sets)
    assert len(groups[(0, 0, 0)]) == 4
    assert len(groups[(3,)]) == 4
    assert len(groups[(4,)]) == 1
    assert len(groups[(0, 2)]) == 12
    # pair x pair: this editor keeps the overlapping pairs that S1 disallows (the 12 products
    # listed on p. 95, pp. 47-48) next to the 3 disjoint ones (3 V2^2); not published in Table 6-10
    assert len(groups[(2, 2)]) == 15
    assert len(result["cutSets"]) == 36 == 4 + 4 + 1 + 12 + 15


def test_v4_the_global_event(result):
    """Table 6-10 p. 105: V4 = 2.9E-5 (formula alpha_4 Q_t, Table 6-5 p. 97)."""
    (cut_set,) = by_type(result)[(4,)]
    assert [e["id"] for e in cut_set["events"]] == ["ccf:g1:V1+V2+V3+V4"]
    assert cut_set["probability"] == published(2.9e-5, 2)
    assert cut_set["probability"] == pytest.approx(ALPHA_TABLE_6_9[3] / SUM * QT, rel=1e-12, abs=0.0)


def test_four_v3_the_triple_events_structure_and_formula(result):
    """Table 6-10 p. 105 prints 4 V3 = 6.6E-5; see the module text for why the value itself
    is not asserted. Four triple events, each a cut set of its own, V3 = alpha_3 / 3 * Q_t."""
    cut_sets = by_type(result)[(3,)]
    assert sorted(e["id"] for cs in cut_sets for e in cs["events"]) == sorted(
        "ccf:g1:" + "+".join(m for m in MEMBERS if m != left_out) for left_out in MEMBERS)
    assert all(len(cs["events"]) == 1 for cs in cut_sets)
    assert total(cut_sets) == pytest.approx(
        4 * ALPHA_TABLE_6_9[2] / 3 / SUM * QT, rel=1e-12, abs=0.0)


def test_twelve_v2_v1_pair_event_times_independent_event(result):
    """Table 6-10 p. 105: 12 V2 V1 = 1.1E-6 (V2 = alpha_2 / 3 Q_t, V1 = alpha_1 Q_t)."""
    cut_sets = by_type(result)[(0, 2)]
    assert len(cut_sets) == 12
    for cut_set in cut_sets:
        pair = next(e["id"] for e in cut_set["events"] if ccf_size(e["id"]) == 2)
        single = next(e["id"] for e in cut_set["events"] if ccf_size(e["id"]) == 0)
        assert single not in pair.split(":")[2].split("+")      # the independent event is another valve
    assert total(cut_sets) == published(1.1e-6, 2)
    v1 = ALPHA_TABLE_6_9[0] / SUM * QT
    v2 = ALPHA_TABLE_6_9[1] / 3 / SUM * QT
    assert total(cut_sets) == pytest.approx(12 * v2 * v1, rel=1e-12, abs=0.0)


def test_four_v1_cubed_independent_triples(result):
    """Table 6-10 p. 105: 4 V1^3 = 2.9E-7."""
    cut_sets = by_type(result)[(0, 0, 0)]
    assert len(cut_sets) == 4
    assert total(cut_sets) == published(2.9e-7, 2)
    v1 = ALPHA_TABLE_6_9[0] / SUM * QT
    assert total(cut_sets) == pytest.approx(4 * v1 ** 3, rel=1e-12, abs=0.0)


# ------------------------------------------------------------------ cases 2 and 3: S1 Table 3-1 p. 13
# DOCUMENTED values: published rounding not reproducible. S1 Table 3-1 rounds coarsely (the printed g
# are the tool values rounded up to two decimals; S1 states no rule); tool value shown, no match
# claimed. Nothing below asserts that the published g equals or bounds the tool value; the tests
# assert the structure (the CCF events that fail the system) and the formula (S1 Eq. 5.6 and
# 5.7-5.9, as the Table 5-4 p. 53 / Table 5-5 p. 54 forms with the m = 4 rows corrected), computed twice.
#
# What g is (S1 Eq. 3.1 and Table 3-1 pp. 12-13): the CCF basic event has probability g * P(A) with
# P(A) = Q_t. S1 p. 48 says "The screening values in Table 3-1 use these formulae [Tables 5-4 and
# 5-5] and the generic estimates discussed later in Section 5.5.4"; Table 3-1 itself says nothing of
# the kind. That the alpha set is Table 5-11 p. 75 (m = 4) is an inference (11 of 12 printed cells of the
# table agree), not a statement of the source. Table 3-1 is labelled by SUCCESS configuration ("k of 4" = k valves must work):
#   "2 of 4"  fails when THREE of the four fail   -> CCF events of 3 or 4 members   (k = 3 gate)
#   "3 of 4"  fails when TWO of the four fail     -> CCF events of 2, 3 or 4 members (k = 2 gate)
# g(tool) = sum of the probabilities of those CCF events (each is a cut set of its own) / Q_t.
#
# Published g (S1 Table 3-1 p. 13), Table 5-11 p. 75 alpha for m = 4 (it also is NASA/SP-2011-3421
# Table 7-1, not consulted here):
ALPHA_TABLE_5_11 = (0.95, 0.0213, 0.0101, 0.0186)
PUBLISHED_G = {   # (testing, k of 4 for success) -> printed g
    ("staggered", 2): 0.04, ("staggered", 3): 0.08,
    ("nonStaggered", 2): 0.11, ("nonStaggered", 3): 0.19,
}
#: failure threshold of the system: number of failed members that fails it = 5 - success k
FAIL_AT = {2: 3, 3: 2}
#: the tool value, printed to 7 decimals (tool value shown; the published g is NOT claimed equal)
TOOL_G = {
    ("staggered", 2): 0.0320667, ("staggered", 3): 0.0746667,
    ("nonStaggered", 2): 0.1046204, ("nonStaggered", 3): 0.1822656,
}
CASES_G = [(testing, success_k) for testing in ("staggered", "nonStaggered") for success_k in (2, 3)]
IDS_G = ["%s-%d-of-4" % (testing, k) for testing, k in CASES_G]


def formula_g(testing, fail_at, alpha=ALPHA_TABLE_5_11):
    """g from the Table 5-4 / 5-5 formulas with the m = 4 rows CORRECTED, written without the
    product code. The m = 4 rows printed in S1 Tables 5-4 and 5-5 are swapped (source error, see
    the SPEC 7.3 error list), so they are not copied: the forms below are derived from Eq. 5.6 and
    Eq. 5.7-5.9. Staggered: 4 a3/3 + a4 (3 failing), 2 a2 + 4 a3/3 + a4 (2 failing). Non-staggered:
    4 (a3 + a4)/a_t and 4 (a2 + a3 + a4)/a_t. The alpha are divided by their sum first (FN-43)."""
    total_alpha = math.fsum(alpha)
    a1, a2, a3, a4 = (x / total_alpha for x in alpha)
    if testing == "staggered":      # Table 5-4: Q_k = alpha_k / C(3, k-1) Q_t
        if fail_at == 3:
            return 4 * a3 / 3 + a4
        return 2 * a2 + 4 * a3 / 3 + a4                  # 6 Q_2 + 4 Q_3 + Q_4
    alpha_t = a1 + 2 * a2 + 3 * a3 + 4 * a4              # Table 5-5, non-staggered
    if fail_at == 3:
        return 4 * (a3 + a4) / alpha_t
    return 4 * (a2 + a3 + a4) / alpha_t


def alpha_group(testing):
    return {"id": "g1", "name": "MOV group", "model": "alpha", "beta": None,
            "alpha": list(ALPHA_TABLE_5_11), "testing": testing, "members": list(MEMBERS),
            "source": "NUREG/CR-5485 Table 5-11 p. 75"}


def g_from_cut_sets(testing, fail_at, qt=1e-3):
    """The tool: the CCF events (one event per cut set) of the k-out-of-4 failure gate, / Q_t."""
    leaf = dict(valve("x"), probability=qt)
    gate = {"id": "G1", "name": "Gate", "type": "Event", "probability": 1.0, "notes": "",
            "links": [], "gateType": "KOFN", "logicGate": "OR", "k": fail_at,
            "children": [dict(leaf, id=i, name="MOV " + i) for i in MEMBERS]}
    root = {"id": "root", "name": "Top event", "type": "Root", "logicGate": "OR",
            "probability": 1.0, "notes": "", "links": [], "children": [gate]}
    out = cutsets.compute(root, {"ccfGroups": [alpha_group(testing)]}, {"timeBudgetS": 120})
    single_ccf = [cs for cs in out["cutSets"]
                  if len(cs["events"]) == 1 and ccf_size(cs["events"][0]["id"]) >= 2]
    return single_ccf, total(single_ccf) / qt


@pytest.mark.parametrize("testing, success_k", CASES_G, ids=IDS_G)
def test_table_3_1_g_structure_and_formula(testing, success_k):
    """S1 Table 3-1 p. 13, "<k> of 4" for success, staggered / non-staggered, alpha of Table 5-11
    p. 75. Published rounding not reproducible: S1 Table 3-1 rounds coarsely (the printed g are the
    tool values rounded up to two decimals; S1 states no rule); tool value shown, no match claimed."""
    fail_at = FAIL_AT[success_k]
    single_ccf, g_tool = g_from_cut_sets(testing, fail_at)
    # structure: every CCF event of fail_at or more members is a cut set of its own
    expected_events = sum(math.comb(4, size) for size in range(fail_at, 5))
    assert len(single_ccf) == expected_events == (5 if fail_at == 3 else 11)
    assert min(ccf_size(cs["events"][0]["id"]) for cs in single_ccf) == fail_at
    # formula: the product agrees with the corrected Table 5-4 / 5-5 forms (relative 1e-12)
    assert g_tool == pytest.approx(formula_g(testing, fail_at), rel=1e-12, abs=0.0)
    # and event_probabilities (the product's expansion) gives the same sum
    expansion = ccf.event_probabilities("alpha", alpha_group(testing), [1e-3] * 4)
    from_events = math.fsum(q for idx, q in expansion.events if len(idx) >= fail_at) / 1e-3
    assert from_events == pytest.approx(g_tool, rel=1e-12, abs=0.0)
    # the tool value shown (half a unit of the 7th decimal); published g is only recorded
    assert abs(g_tool - TOOL_G[(testing, success_k)]) <= 5e-8, g_tool


def test_table_3_1_published_g_are_recorded_for_the_three_reference_cases():
    """Case 2: staggered, 2 of 4 g 0.04 and 3 of 4 g 0.08; case 3: non-staggered, 2 of 4 g 0.11 and
    3 of 4 g 0.19 (S1 Table 3-1 p. 13), alpha (0.95, 0.0213, 0.0101, 0.0186) (S1 Table 5-11 p. 75).
    Recorded only: the alpha values sum to 1 as printed, so no normalisation warning arises."""
    assert math.fsum(ALPHA_TABLE_5_11) == pytest.approx(1.0, rel=1e-12, abs=0.0)
    for testing in ("staggered", "nonStaggered"):
        (assessment,) = ccf.assess([alpha_group(testing)], tree(), {"ccfGroups": [alpha_group(testing)]}, "FTA")
        assert assessment.applied and [f.code for f in assessment.findings] == []
