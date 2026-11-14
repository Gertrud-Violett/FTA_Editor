"""F2 BRIEF criteria 7, 8, 9 and 10 (FN-19, FN-21, FN-22, FN-66): the expansion.

Reference cases of SPEC 7.4 (Q_t = 1e-3, group g1 "Feed pumps", beta 0.1, members A and B):

====  ===================================  ====================================
R1    root OR [G1 AND [A, B], C], C q 0    rare-event 1.0081e-4 (rel 1e-12)
R1h   same                                 MCUB 1.00809919e-4 (rel 1e-9)
R2    root OR [A, B]                       rare-event 1.9e-3 (rel 1e-12)
R2h   same                                 MCUB 1.899010081e-3 (rel 1e-9)
R3    R1 with beta 0                       MCUB 1e-6 = the tree without the group
R4    R1 with beta 1                       top 1e-3
====  ===================================  ====================================

Tolerances exactly as SPEC 7.4; (1 - 0.1) * 1e-3 is 9.000000000000001e-4, so a
float is never compared with ``==``.

The seams of DESIGN section 6 make the "budget exceeded" cases deterministic: a
tiny tree never reaches the time check, so ``cutsets.compute`` is replaced by a
function that raises ``CutsetError('time', ...)`` or ``RuntimeError``, and the
summary cap is made to fire with ``engine.SUMMARY_LIMITS['maxCount'] = 1``.
"""
import pytest

import _ccf_models as M

LIMITS = {"timeBudgetS": 120}
R1_RARE = 1.0081e-4
R1_MCUB = 1.00809919e-4
R2_RARE = 1.9e-3
R2_MCUB = 1.899010081e-3
#: 2-of-3 over A, B, D in one beta 0.1 group, Q_t 1e-3 (NUREG/CR-5485 Table 5-2 p. 49, Case 4,
#: Q_2 = 0): rare-event 1e-4 + 3 (9e-4)^2; MCUB 1 - (1 - 1e-4)(1 - 8.1e-7)^3 in exact Fractions.
TWO_OF_THREE_RARE = 1.0243e-4
TWO_OF_THREE_MCUB = 1.0242975503e-4
#: FN-66 leaf with links (R0 (a)). X: q 0.1 with AND links to A and B, beta 0.1 group {A, B},
#: Q_t 1e-3. X's expanded cut sets are {X, C} = 0.1 * 1e-4 = 1e-5 and {X, A', B'} = 0.1 *
#: (9e-4)^2 = 8.1e-8, so X = 1 - (1 - 1e-5)(1 - 8.1e-8) = 1.008099919e-5 (exact Fractions). The
#: tree walk gives 0.1 * 1e-3 * 1e-3 = 1e-7, a hundred times too low: it must never be shown.
X_MCUB = 1.008099919e-5
X_TREE_WALK = 1e-7
#: A member A that carries an AND link to the member B: {C}, {A', B'}: 1 - (1 - 1e-4)(1 - 8.1e-7)
#: = 1.00809919e-4 (the R1h number); its tree walk is Q_t * Q_t = 1e-6.
A_AND_B_TREE_WALK = 1e-6
REL12 = 1e-12
REL9 = 1e-9


def analysis_of(groups):
    return {"ccfGroups": groups}


def compute(tree, groups):
    from fta_web import cutsets

    return cutsets.compute(tree, analysis_of(groups), LIMITS)


def summary(tree, groups):
    from fta_web import engine

    return engine.summary(tree, analysis_of(groups))


@pytest.fixture
def compute_times_out(monkeypatch):
    from fta_web import cutsets

    def fail(*args, **kwargs):
        raise cutsets.CutsetError("time", "The cut-set time budget ran out.")

    monkeypatch.setattr(cutsets, "compute", fail)


@pytest.fixture
def compute_errors(monkeypatch):
    from fta_web import cutsets

    def fail(*args, **kwargs):
        raise RuntimeError("the cut sets failed")

    monkeypatch.setattr(cutsets, "compute", fail)


@pytest.fixture
def summary_cap(monkeypatch):
    from fta_web import engine

    monkeypatch.setitem(engine.SUMMARY_LIMITS, "maxCount", 1)


# ---------------------------------------------------------------- criterion 7


def test_r1_cut_sets_and_rare_event_sum():
    result = compute(M.r1_tree(), [M.group()])
    assert result["total"] == 2
    assert sorted(M.cut_set_ids(result)) == [["A", "B"], ["ccf:g1"]]
    assert M.find_cut_set(result, ["ccf:g1"])["probability"] == M.rel(1e-4, REL12)
    assert M.find_cut_set(result, ["A", "B"])["probability"] == M.rel(8.1e-7, REL12)
    assert result["rareEvent"] == M.rel(R1_RARE, REL12)
    assert "ccf:g1" in {r["id"] for r in result["repeatedEvents"]}


def test_r1h_min_cut_upper_bound():
    result = compute(M.r1_tree(), [M.group()])
    assert result["mcub"] == M.rel(R1_MCUB, REL9)


def test_r2_rare_event_sum_of_two_members_in_or():
    result = compute(M.r2_tree(), [M.group()])
    assert sorted(M.cut_set_ids(result)) == [["A"], ["B"], ["ccf:g1"]]
    assert result["rareEvent"] == M.rel(R2_RARE, REL12)  # 2 Q_1 + Q_2


def test_r2h_min_cut_upper_bound():
    assert compute(M.r2_tree(), [M.group()])["mcub"] == M.rel(R2_MCUB, REL9)


def test_r3_beta_zero_equals_the_tree_without_the_group():
    with_group = compute(M.r1_tree(), [M.group(beta=0.0)])
    without = compute(M.r1_tree(), [])
    assert [g["id"] for g in with_group["ccf"]["applied"]] == ["g1"]  # beta 0 is applied
    assert with_group["mcub"] == M.rel(1e-6, REL9)
    assert with_group["mcub"] == M.rel(without["mcub"], REL9)

    def kept(result):
        rows = {}
        for cs in result["cutSets"]:
            ids = tuple(sorted(e["id"] for e in cs["events"]))
            if any(i.startswith("ccf:") for i in ids) and cs["probability"] == 0:
                continue  # a CCF set with probability zero is dropped
            rows[ids] = cs["probability"]
        return rows

    a, b = kept(with_group), kept(without)
    assert set(a) == set(b) == {("A", "B")}
    assert a[("A", "B")] == M.rel(b[("A", "B")], REL12)


def test_r4_beta_one_gives_the_member_probability_as_top():
    result = compute(M.r1_tree(), [M.group(beta=1.0)])
    assert result["mcub"] == M.rel(1e-3, REL9)
    assert summary(M.r1_tree(), [M.group(beta=1.0)])["headline"] == M.rel(1e-3, REL9)


def two_of_three_tree():
    """root OR [ V KOFN 2-of-3 [A, B, D] ]: A, B and D are all members of the one group."""
    return M.top([M.gate("V", "KOFN", [M.pump("A"), M.pump("B"), M.pump("D")],
                         name="Two of three pumps fail", k=2)])


def test_the_two_of_three_reference_case_has_the_ccf_event_and_the_three_pairs():
    """FN-19, NUREG/CR-5485 Table 5-2 p. 49, Case 4, with Q_2 = 0 (a beta-factor group has no
    partial CCF events): 2-of-3 over A, B, D, beta 0.1, Q_t 1e-3 each.

    Each member is A' (independent part Q_1 = 9e-4) or the CCF event C (Q_m = beta Q_t = 1e-4).
    (A' + C)(B' + C) = A'B' + C, so the cut sets are {C}, {A', B'}, {A', D'}, {B', D'}.
    Rare-event sum = 1e-4 + 3 * (9e-4)^2 = 1e-4 + 2.43e-6 = 1.0243e-4 (rel 1e-12).
    MCUB = 1 - (1 - 1e-4)(1 - 8.1e-7)^3 = 1.0242975503e-4 (exact rational arithmetic, rel 1e-9).
    """
    group = M.group(members=["A", "B", "D"])
    result = compute(two_of_three_tree(), [group])
    assert result["total"] == 4
    assert sorted(M.cut_set_ids(result)) == [["A", "B"], ["A", "D"], ["B", "D"], ["ccf:g1"]]
    ccf_set = M.find_cut_set(result, ["ccf:g1"])
    assert ccf_set["probability"] == M.rel(1e-4, REL12)  # beta Q_t
    (event,) = ccf_set["events"]
    assert event["q"] == M.rel(1e-4, REL12)
    for ids in (["A", "B"], ["A", "D"], ["B", "D"]):
        pair = M.find_cut_set(result, ids)
        assert pair["probability"] == M.rel(8.1e-7, REL12)  # (9e-4)^2
        assert len(pair["events"]) == 2
        for e in pair["events"]:
            assert e["q"] == M.rel(9e-4, REL12)  # (1 - beta) Q_t
            assert e["ccf"]["groupId"] == "g1" and e["ccf"]["role"] == "independent"
    assert result["rareEvent"] == M.rel(TWO_OF_THREE_RARE, REL12)  # 1.0243e-4
    assert result["mcub"] == M.rel(TWO_OF_THREE_MCUB, REL9)  # 1.02429755e-4
    out = summary(two_of_three_tree(), [group])
    assert out["headline"] == M.rel(TWO_OF_THREE_MCUB, REL9)


def test_the_compiled_operators_are_in_topological_order_and_events_have_their_parts():
    from fta_web import logic

    s = logic.compile_tree(M.r1_tree(), analysis_of([M.group()]))
    for index, op in enumerate(s.ops):
        assert all(child < index for child in logic.op_children(op)), (index, op)
    # first-reference order, the CCF event right after the first member's slot (DESIGN 4, 5)
    assert [e["id"] for e in s.events] == ["A", "ccf:g1", "B", "C"]
    by_id = {e["id"]: e for e in s.events}
    assert by_id["A"]["q"] == M.rel(9e-4, REL12)
    assert by_id["B"]["q"] == M.rel(9e-4, REL12)
    assert by_id["ccf:g1"]["q"] == M.rel(1e-4, REL12)
    assert by_id["A"]["derived"]["q"] == M.rel(1e-3, REL12)  # Q_t is kept
    assert by_id["A"]["name"] == "Pump A (independent part)"
    assert by_id["ccf:g1"]["name"] == "CCF: Feed pumps"
    assert by_id["ccf:g1"]["quant"] is None  # the CCF event has no uncertainty of its own
    assert by_id["C"]["q"] == 0.0 and "ccf" not in by_id["C"]


def test_a_tree_without_groups_compiles_exactly_as_before():
    from fta_web import logic

    plain = logic.compile_tree(M.r1_tree(), None)
    with_empty = logic.compile_tree(M.r1_tree(), analysis_of([]))
    assert plain.ops == with_empty.ops and plain.event_ids() == ["A", "B", "C"]
    assert all("ccf" not in e for e in plain.events)


def test_the_301_node_fixture_compiles_in_order_with_ten_ccf_events(repo_root):
    import json

    from fta_web import logic

    doc = json.loads((repo_root / "fta_web" / "tests" / "fixtures" / "perf_ccf_301.json")
                     .read_text(encoding="utf-8"))
    s = logic.compile_tree(doc["tree"], doc["analysis"])
    for index, op in enumerate(s.ops):
        assert all(child < index for child in logic.op_children(op)), index
    ccf_ids = [e["id"] for e in s.events if e["id"].startswith("ccf:")]
    assert sorted(ccf_ids) == sorted("ccf:G%d" % k for k in range(1, 11))
    assert len(ccf_ids) == len(set(ccf_ids))


def linked_tree():
    """A is reached again by a link from D (under another gate)."""
    return M.top([
        M.gate("G1", "AND", [M.pump("A"), M.pump("B")], name="Pumps fail"),
        M.gate("G2", "AND", [M.leaf("C"), M.leaf("D", 1e-3, links=[
            {"target_id": "A", "relation": "OR"}])], name="Other"),
    ])


def transferred_tree():
    """The sub tree holding A and B is reached again by a transfer gate."""
    return M.top([
        M.gate("SUB", "AND", [M.pump("A"), M.pump("B")], name="Sub tree"),
        M.gate("G2", "AND", [M.leaf("C"), M.leaf("XF", 1.0, name="Transfer to sub",
                                                 gateType="TRANSFER", transferTo="SUB")],
               name="Other"),
    ])


def test_a_member_linked_under_two_gates_gives_exactly_one_ccf_id():
    from fta_web import logic

    result = compute(linked_tree(), [M.group()])
    assert sorted(M.cut_set_ids(result)) == [["A", "B"], ["A", "C"], ["C", "D"], ["ccf:g1"]]
    ccf_ids = {e["id"] for cs in result["cutSets"] for e in cs["events"]
               if e["id"].startswith("ccf:")}
    assert ccf_ids == {"ccf:g1"}
    s = logic.compile_tree(linked_tree(), analysis_of([M.group()]))
    assert [e["id"] for e in s.events if e["id"].startswith("ccf:")] == ["ccf:g1"]
    assert {r["id"] for r in result["repeatedEvents"]} >= {"A", "ccf:g1"}


def test_a_member_reached_by_a_transfer_gives_exactly_one_ccf_id():
    from fta_web import logic

    result = compute(transferred_tree(), [M.group()])
    assert sorted(M.cut_set_ids(result)) == [["A", "B"], ["ccf:g1"]]
    s = logic.compile_tree(transferred_tree(), analysis_of([M.group()]))
    assert [e["id"] for e in s.events if e["id"].startswith("ccf:")] == ["ccf:g1"]
    for index, op in enumerate(s.ops):
        assert all(child < index for child in logic.op_children(op))


def test_a_group_that_is_not_applied_leaves_the_tree_as_it_was():
    from fta_web import logic

    bad = [M.group(beta="abc")]
    s = logic.compile_tree(M.r1_tree(), analysis_of(bad))
    assert s.event_ids() == ["A", "B", "C"]
    result = compute(M.r1_tree(), bad)
    assert result["mcub"] == M.rel(1e-6, REL9)
    assert [g["code"] for g in result["ccf"]["notApplied"]] == ["CCF_BAD_PARAMETER"]


# ---------------------------------------------------------------- criterion 8


def test_an_applied_group_makes_the_headline_the_mcub_that_includes_ccf():
    from fta_web import engine

    tree = M.r1_tree()
    out = summary(tree, [M.group()])
    assert out["headlineMethod"] == "mcub"
    assert out["headline"] == M.rel(R1_MCUB, REL9)
    assert out["mcub"] == M.rel(R1_MCUB, REL9)
    assert out["rareEvent"] == M.rel(R1_RARE, REL12)
    assert out["treeWalk"] == M.rel(1e-6, REL9)  # the tree walk stays CCF-free
    assert out["ccfIncomplete"] is False
    assert [g["id"] for g in out["ccf"]["applied"]] == ["g1"]
    assert "ccf:g1" in {r["id"] for r in out["repeatedEvents"]}
    assert engine.may_need_cut_sets(tree, analysis_of([M.group()])) is True
    assert engine.may_need_cut_sets(tree) is False  # no repeated event and no group


def test_the_headline_is_the_mcub_also_when_the_tree_has_no_repeated_event():
    out = summary(M.r2_tree(), [M.group()])
    assert out["headlineMethod"] == "mcub"
    assert out["headline"] == M.rel(R2_MCUB, REL9)
    from fta_web import engine

    assert engine.summary(M.r2_tree(), {})["headlineMethod"] == "treeWalk"  # without a group


def test_may_need_cut_sets_ignores_a_group_that_is_not_applied():
    from fta_web import engine

    assert engine.may_need_cut_sets(M.r2_tree(), analysis_of([M.group(beta="abc")])) is False


def test_a_summary_without_groups_has_the_1_8_1_keys_and_no_ccf_key():
    out = summary(M.r1_tree(), [])
    assert set(out) == {"treeWalk", "mcub", "rareEvent", "headline", "headlineMethod",
                        "repeatedEvents", "nonCoherent", "approximations", "truncated",
                        "truncatedBy", "capped", "elapsedMs"}
    assert out["headlineMethod"] == "treeWalk"


INCOMPLETE = [
    ("time", "compute_times_out", ["time"], True),
    ("error", "compute_errors", ["error"], False),
    ("summary cap", "summary_cap", [], True),
]


@pytest.mark.parametrize("reason, seam, truncated_by, capped", INCOMPLETE,
                         ids=[i[0] for i in INCOMPLETE])
def test_incomplete_cut_sets_give_a_null_headline_never_a_plain_number(
        request, reason, seam, truncated_by, capped):
    request.getfixturevalue(seam)
    out = summary(M.r1_tree(), [M.group()])
    assert out["headline"] is None
    assert out["headlineMethod"] == "incomplete"
    assert out["mcub"] is None and out["rareEvent"] is None
    assert out["ccfIncomplete"] is True
    assert out["ccfIncompleteReason"] == reason
    assert out["treeWalk"] == M.rel(1e-6, REL9)  # kept, labelled "without CCF"
    assert out["capped"] is capped
    assert out["truncatedBy"] == truncated_by
    assert [g["id"] for g in out["ccf"]["applied"]] == ["g1"]
    assert out["ccfGates"] == {"G1": {"method": "na"}, "root": {"method": "na"}}


@pytest.mark.parametrize("seam", ["compute_times_out", "compute_errors", "summary_cap"])
def test_a_document_whose_groups_are_all_not_applied_keeps_the_1_8_1_headline(request, seam):
    request.getfixturevalue(seam)
    out = summary(M.r1_tree(), [M.group(beta="abc")])
    assert out["headlineMethod"] == "treeWalk"
    assert out["headline"] == M.rel(1e-6, REL9)
    assert out["ccfIncomplete"] is False
    assert "ccfGates" not in out
    assert [g["id"] for g in out["ccf"]["notApplied"]] == ["g1"]


def test_incomplete_summary_through_the_api(api, compute_times_out):
    api.open_doc(M.document(M.r1_tree("api incomplete"), [M.group()]))
    status, out = api.get("/api/analysis/summary")
    assert status == 200, out
    assert out["headline"] is None and out["headlineMethod"] == "incomplete"
    assert out["ccfIncomplete"] is True and out["ccfIncompleteReason"] == "time"
    assert out["ccfGates"]["G1"] == {"method": "na"}


# ---------------------------------------------------------------- criterion 9


def test_cut_sets_list_the_ccf_event_and_the_independent_parts_with_their_labels(api):
    api.open_doc(M.document(M.r1_tree(), [M.group()]))
    status, body = api.post("/api/analysis/cutsets", {})
    assert status == 200, body
    ccf_set = M.find_cut_set(body, ["ccf:g1"])
    (event,) = ccf_set["events"]
    assert event["name"] == "CCF: Feed pumps"
    assert event["q"] == M.rel(1e-4, REL12)
    assert event["ccf"]["groupId"] == "g1" and event["ccf"]["role"] == "event"
    assert event["ccf"]["members"] == ["A", "B"]
    pair = M.find_cut_set(body, ["A", "B"])
    assert pair["probability"] == M.rel(8.1e-7, REL12)  # 9e-4 * 9e-4
    names = {e["id"]: e["name"] for e in pair["events"]}
    assert names == {"A": "Pump A (independent part)", "B": "Pump B (independent part)"}
    for e in pair["events"]:
        assert e["q"] == M.rel(9e-4, REL12)
        assert e["ccf"]["groupId"] == "g1" and e["ccf"]["role"] == "independent"
    assert {"id": "ccf:g1", "name": "CCF: Feed pumps"} in body["repeatedEvents"]
    assert [g["id"] for g in body["ccf"]["applied"]] == ["g1"]
    assert body["ccf"]["note"] == M.NOTE_EN


def test_a_document_without_groups_has_no_ccf_marker_and_no_ccf_block(api):
    api.open_doc(M.document(M.r1_tree(), None))
    status, body = api.post("/api/analysis/cutsets", {})
    assert status == 200, body
    assert "ccf" not in body
    assert all("ccf" not in e for cs in body["cutSets"] for e in cs["events"])


# --------------------------------------------------------------- criterion 10


def test_gates_above_a_member_show_the_mcub_of_the_cut_sets_not_the_tree_walk():
    tree = M.top([
        M.gate("SYS", "OR", [M.gate("G1", "AND", [M.pump("A"), M.pump("B")], name="Pumps fail"),
                             M.leaf("C", 0.0)], name="System"),
        M.gate("OTHER", "AND", [M.leaf("E"), M.leaf("F")], name="Other"),
    ])
    out = summary(tree, [M.group()])
    gates = out["ccfGates"]
    assert set(gates) == {"G1", "SYS", "root"}  # not the leaves, not OTHER (no member below)
    g1 = 1 - (1 - 1e-4) * (1 - 8.1e-7)
    for key in ("G1", "SYS"):
        assert gates[key]["method"] == "mcub"
        assert gates[key]["value"] == M.rel(g1, REL9)
    assert gates["G1"]["value"] == M.rel(R1_MCUB, REL9)
    assert gates["root"]["method"] == "mcub"
    assert gates["root"]["value"] == out["mcub"]  # the top uses the summary's value exactly
    assert gates["root"]["value"] == M.rel(1 - (1 - 1e-4) * (1 - 8.1e-7) * (1 - 1e-6), REL9)
    assert gates["G1"]["value"] != M.rel(1e-6, 0.5)  # never the tree-walk value


def test_g1_shows_the_mcub_of_r1h_in_the_api(api):
    api.open_doc(M.document(M.r1_tree(), [M.group()]))
    status, out = api.get("/api/analysis/summary")
    assert status == 200, out
    assert out["ccfGates"]["G1"]["method"] == "mcub"
    assert out["ccfGates"]["G1"]["value"] == M.rel(R1_MCUB, REL9)  # 1.00809919e-4
    assert out["ccfGates"]["root"]["value"] == out["mcub"]
    assert "A" not in out["ccfGates"] and "B" not in out["ccfGates"] and "C" not in out["ccfGates"]


def dot_of(api, style="compact"):
    status, body = api.get("/api/dot?style=%s" % style)
    assert status == 200, body
    return body, body["dot"]


def test_the_diagram_shows_the_mcub_of_a_gate_above_a_member(api):
    api.open_doc(M.document(M.r1_tree(), [M.group()]))
    body, dot = dot_of(api)
    assert body["ccfGates"] is True
    shown = M.fmt(R1_MCUB)  # 1.01e-4
    assert dot.count("P_calc:%s (MCUB)" % shown) == 2  # G1 and the root (also above a member)
    assert "P_calc:%s" % M.fmt(1e-6) not in dot  # not the tree-walk value of G1 or the root
    assert "tree walk" not in dot
    symbols_body, symbols = dot_of(api, "symbols")
    assert symbols.count("Q=%s (MCUB)" % shown) == 2
    assert "Q=%s" % M.fmt(1e-6) not in symbols


def test_the_diagram_shows_na_ccf_and_no_number_when_the_cut_sets_are_incomplete(
        api, compute_times_out):
    api.open_doc(M.document(M.r1_tree("diagram incomplete"), [M.group()]))
    body, dot = dot_of(api)
    assert body["ccfGates"] is True
    assert dot.count("P_calc:n/a (CCF)") == 2
    assert "P_calc:%s" % M.fmt(1e-6) not in dot
    assert "tree walk" not in dot and "(MCUB)" not in dot
    _, symbols = dot_of(api, "symbols")
    assert symbols.count("Q=n/a (CCF)") == 2


def test_a_member_box_shows_q_t_and_the_independent_part_beside_it(api):
    api.open_doc(M.document(M.r1_tree("member box"), [M.group()]))
    _, dot = dot_of(api)
    assert dot.count("(indep. %s)" % M.fmt(9e-4)) == 2  # "indep. 9.00e-4": Pump A and Pump B
    assert "P:%s (indep." % M.fmt(1e-3) in dot  # Q_t stays
    _, symbols = dot_of(api, "symbols")
    assert symbols.count("(indep. %s)" % M.fmt(9e-4)) == 2


def test_a_group_that_is_not_applied_shows_no_independent_part_and_no_ccf_gate_value(api):
    api.open_doc(M.document(M.r1_tree("not applied"), [M.group(beta="abc")]))
    body, dot = dot_of(api)
    assert body["ccfGates"] is False
    assert "(indep." not in dot and "n/a (CCF)" not in dot and "(MCUB)" not in dot


def test_the_report_diagram_shows_the_same_gate_values(api):
    from fta_web import report_docx
    from fta_web.state import get_state

    api.open_doc(M.document(M.r1_tree("report diagram"), [M.group()]))
    dot = report_docx.diagram_dot_text(get_state().core, 3)
    assert dot.count("P_calc:%s (MCUB)" % M.fmt(R1_MCUB)) == 2
    assert "P_calc:%s" % M.fmt(1e-6) not in dot


def test_the_report_diagram_shows_na_ccf_when_incomplete(api, compute_times_out):
    from fta_web import report_docx
    from fta_web.state import get_state

    api.open_doc(M.document(M.r1_tree("report diagram incomplete"), [M.group()]))
    dot = report_docx.diagram_dot_text(get_state().core, 3)
    assert dot.count("P_calc:n/a (CCF)") == 2
    assert "P_calc:%s" % M.fmt(1e-6) not in dot


def events_sheet(blob):
    """{node id: {header: value}} of the Events sheet."""
    cells = M.xlsx_cells(blob)
    rows = {}
    for sheet, row, column, value in cells:
        if sheet == "Events":
            rows.setdefault(row, {})[column] = value
    header = rows.pop(1)
    names = {col: name for col, name in header.items()}
    table = {}
    for row in rows.values():
        record = {names[col]: value for col, value in row.items() if col in names}
        table[record["Id"]] = record
    return table


def export_xlsx(api):
    status, blob = api.binary("GET", "/api/export/xlsx")
    assert status == 200
    return blob


def test_the_excel_sheets_show_the_mcub_of_the_gate_above_a_member(api):
    api.open_doc(M.document(M.r1_tree("excel"), [M.group()]))
    blob = export_xlsx(api)
    table = events_sheet(blob)
    assert table["G1"]["Calculated probability"] == M.rel(R1_MCUB, REL9)
    assert table["root"]["Calculated probability"] == M.rel(R1_MCUB, REL9)
    assert table["A"]["Calculated probability"] == M.rel(1e-3, REL12)  # Q_t
    texts = [str(v) for *_, v in M.xlsx_cells(blob)]
    pumps = [t for t in texts if t.startswith("Pumps fail\n(")]
    assert pumps and all("(MCUB, CCF)" in t and "1e-06" not in t for t in pumps)
    assert any(t.startswith("CCF groups applied") for t in texts)


def test_the_excel_sheets_show_na_ccf_when_incomplete(api, compute_times_out):
    api.open_doc(M.document(M.r1_tree("excel incomplete"), [M.group()]))
    blob = export_xlsx(api)
    table = events_sheet(blob)
    assert table["G1"]["Calculated probability"] == "n/a (CCF)"
    assert table["root"]["Calculated probability"] == "n/a (CCF)"
    texts = [str(v) for *_, v in M.xlsx_cells(blob)]
    pumps = [t for t in texts if t.startswith("Pumps fail\n(")]
    assert pumps and all("n/a (CCF)" in t and "1e-06" not in t for t in pumps)


def test_the_excel_analysis_sheet_lists_a_group_that_is_not_applied(api):
    api.open_doc(M.document(M.r1_tree("excel not applied"), [M.group(beta="abc")]))
    texts = [str(v) for *_, v in M.xlsx_cells(export_xlsx(api))]
    assert any(t.startswith("CCF groups not applied") for t in texts)
    assert not any("(MCUB, CCF)" in t for t in texts)


# ------------------------------------- criterion 10 again: a leaf with links (FN-66, R0 (a))
#
# A node whose compiled operator is not its own variable is a gate for FN-66, although it has no
# child: a basic event with AND/OR links, and a CCF member with links. It shows the MCUB of its
# expanded cut sets (or n/a (CCF)), never its tree-walk value.


def and_links(*targets):
    return [{"target_id": t, "relation": "AND"} for t in targets]


def x_tree():
    """root OR [ G1 OR [A, B], X ]; X is a basic event, q 0.1, with AND links to A and B."""
    return M.top([
        M.gate("G1", "OR", [M.pump("A"), M.pump("B")], name="Pumps fail"),
        M.leaf("X", 0.1, name="Leaf X", links=and_links("A", "B")),
    ])


def member_links_tree():
    """root OR [ A, B ]; the member A carries an AND link to the member B (A is "A and B")."""
    return M.top([M.pump("A", links=and_links("B")), M.pump("B")])


def test_x_leaf_with_links_shows_its_mcub_in_the_api_gate_values():
    out = summary(x_tree(), [M.group()])
    gates = out["ccfGates"]
    assert set(gates) == {"G1", "X", "root"}  # X is a gate here; the bare members are not
    assert gates["X"]["method"] == "mcub"
    assert gates["X"]["value"] == M.rel(X_MCUB, REL9)  # 1.008099919e-5
    assert gates["X"]["value"] != M.rel(X_TREE_WALK, 0.5)  # never the tree walk
    for key in ("G1", "root"):  # X's sets {X, C}, {X, A', B'} are absorbed by {C}, {A'}, {B'}
        assert gates[key]["method"] == "mcub"
        assert gates[key]["value"] == M.rel(R2_MCUB, REL9)
    assert gates["root"]["value"] == out["mcub"]


def test_x_leaf_with_links_shows_na_ccf_when_the_cut_sets_are_incomplete(compute_times_out):
    out = summary(x_tree(), [M.group()])
    assert out["ccfGates"] == {"G1": {"method": "na"}, "X": {"method": "na"},
                               "root": {"method": "na"}}


def test_x_leaf_with_links_shows_the_mcub_in_the_diagram(api):
    api.open_doc(M.document(x_tree(), [M.group()]))
    body, dot = dot_of(api)
    assert body["ccfGates"] is True
    assert dot.count("P_calc:%s (MCUB)" % M.fmt(X_MCUB)) == 1  # 1.01e-05: X only
    assert dot.count("P_calc:%s (MCUB)" % M.fmt(R2_MCUB)) == 2  # G1 and the root
    assert M.fmt(X_TREE_WALK) not in dot  # 1.00e-07, the tree walk, appears nowhere
    assert "tree walk" not in dot
    _, symbols = dot_of(api, "symbols")
    assert symbols.count("Q=%s (MCUB)" % M.fmt(X_MCUB)) == 1
    assert symbols.count("Q=%s (MCUB)" % M.fmt(R2_MCUB)) == 2
    assert M.fmt(X_TREE_WALK) not in symbols


def test_x_leaf_with_links_shows_na_ccf_in_the_diagram_when_incomplete(api, compute_times_out):
    api.open_doc(M.document(x_tree(), [M.group()]))
    _, dot = dot_of(api)
    assert dot.count("P_calc:n/a (CCF)") == 3  # G1, X and the root
    assert M.fmt(X_TREE_WALK) not in dot and "(MCUB)" not in dot
    _, symbols = dot_of(api, "symbols")
    assert symbols.count("Q=n/a (CCF)") == 3
    assert M.fmt(X_TREE_WALK) not in symbols


def test_x_leaf_with_links_shows_the_mcub_in_the_report_diagram(api):
    from fta_web import report_docx
    from fta_web.state import get_state

    api.open_doc(M.document(x_tree(), [M.group()]))
    dot = report_docx.diagram_dot_text(get_state().core, 3)
    assert dot.count("P_calc:%s (MCUB)" % M.fmt(X_MCUB)) == 1
    assert dot.count("P_calc:%s (MCUB)" % M.fmt(R2_MCUB)) == 2
    assert M.fmt(X_TREE_WALK) not in dot


def test_x_leaf_with_links_shows_na_ccf_in_the_report_diagram_when_incomplete(
        api, compute_times_out):
    from fta_web import report_docx
    from fta_web.state import get_state

    api.open_doc(M.document(x_tree(), [M.group()]))
    dot = report_docx.diagram_dot_text(get_state().core, 3)
    assert dot.count("P_calc:n/a (CCF)") == 3
    assert M.fmt(X_TREE_WALK) not in dot


def test_x_leaf_with_links_shows_the_mcub_in_the_excel_sheets(api):
    api.open_doc(M.document(x_tree(), [M.group()]))
    blob = export_xlsx(api)
    table = events_sheet(blob)
    assert table["X"]["Calculated probability"] == M.rel(X_MCUB, REL9)
    assert table["X"]["Base probability"] == M.rel(0.1, REL12)  # q stays
    assert table["G1"]["Calculated probability"] == M.rel(R2_MCUB, REL9)
    assert table["root"]["Calculated probability"] == M.rel(R2_MCUB, REL9)
    assert table["A"]["Calculated probability"] == M.rel(1e-3, REL12)  # Q_t
    texts = [str(v) for *_, v in M.xlsx_cells(blob)]
    leaf_x = [t for t in texts if t.startswith("Leaf X\n(")]  # the FTA sheet's cell of X
    assert leaf_x and all("(MCUB, CCF)" in t and "1e-07" not in t for t in leaf_x)


def test_x_leaf_with_links_shows_na_ccf_in_the_excel_sheets_when_incomplete(
        api, compute_times_out):
    api.open_doc(M.document(x_tree(), [M.group()]))
    blob = export_xlsx(api)
    table = events_sheet(blob)
    assert table["X"]["Calculated probability"] == "n/a (CCF)"
    assert table["G1"]["Calculated probability"] == "n/a (CCF)"
    texts = [str(v) for *_, v in M.xlsx_cells(blob)]
    leaf_x = [t for t in texts if t.startswith("Leaf X\n(")]
    assert leaf_x and all("n/a (CCF)" in t and "1e-07" not in t for t in leaf_x)


def test_a_member_with_links_shows_the_mcub_of_its_expansion_never_the_tree_walk(api):
    """A is a member of {A, B} and carries an AND link to B, so the node A means "A and B".

    Expanded: (A' + C)(B' + C) = A'B' + C, so A = 1 - (1 - 1e-4)(1 - 8.1e-7) = 1.00809919e-4
    (the R1h number); the tree walk gives Q_t * Q_t = 1e-6. The member keeps its Q_t as the
    base probability and its independent part. With complete cut sets FN-66 asks for the MCUB
    of the node's expanded operator (derived by hand above), so this test asks for that number
    and not merely for "anything but the tree walk"; n/a (CCF) is for incomplete cut sets only.
    """
    api.open_doc(M.document(member_links_tree(), [M.group()]))
    status, out = api.get("/api/analysis/summary")
    assert status == 200, out
    gates = out["ccfGates"]
    assert set(gates) == {"A", "root"}  # B is a bare member: no link, no gate value
    assert gates["A"]["method"] == "mcub"
    assert gates["A"]["value"] == M.rel(R1_MCUB, REL9)
    assert gates["A"]["value"] != M.rel(A_AND_B_TREE_WALK, 0.5)
    _, dot = dot_of(api)
    assert "P:%s (indep. %s) | P_calc:%s (MCUB)" % (
        M.fmt(1e-3), M.fmt(9e-4), M.fmt(R1_MCUB)) in dot
    assert M.fmt(A_AND_B_TREE_WALK) not in dot  # 1.00e-06 appears nowhere
    _, symbols = dot_of(api, "symbols")
    assert "Q=%s (MCUB)" % M.fmt(R1_MCUB) in symbols
    assert M.fmt(A_AND_B_TREE_WALK) not in symbols
    blob = export_xlsx(api)
    table = events_sheet(blob)
    assert table["A"]["Calculated probability"] == M.rel(R1_MCUB, REL9)
    assert table["A"]["Base probability"] == M.rel(1e-3, REL12)  # Q_t
    assert table["B"]["Calculated probability"] == M.rel(1e-3, REL12)
    texts = [str(v) for *_, v in M.xlsx_cells(blob)]
    pump_a = [t for t in texts if t.startswith("Pump A\n(")]  # the FTA sheet's cell of A
    assert pump_a and all("(MCUB, CCF)" in t and "1e-06" not in t for t in pump_a)


def test_a_member_with_links_shows_na_ccf_when_incomplete(api, compute_times_out):
    api.open_doc(M.document(member_links_tree(), [M.group()]))
    status, out = api.get("/api/analysis/summary")
    assert status == 200, out
    assert out["ccfGates"] == {"A": {"method": "na"}, "root": {"method": "na"}}
    _, dot = dot_of(api)
    assert dot.count("P_calc:n/a (CCF)") == 2  # A and the root
    assert M.fmt(A_AND_B_TREE_WALK) not in dot
    blob = export_xlsx(api)
    assert events_sheet(blob)["A"]["Calculated probability"] == "n/a (CCF)"
    texts = [str(v) for *_, v in M.xlsx_cells(blob)]
    pump_a = [t for t in texts if t.startswith("Pump A\n(")]
    assert pump_a and all("n/a (CCF)" in t and "1e-06" not in t for t in pump_a)
