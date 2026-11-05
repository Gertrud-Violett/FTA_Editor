"""F4 BRIEF criterion 4 (FN-55): a factor f scales the event's main parameter.

``POST /api/whatif`` (DESIGN 3 and 4): f multiplies lambda for ``rate``, ``standby``
and ``repairable`` and q for ``fixed``, as Monte Carlo does
(``uncertainty._q_function``); q then follows from the model; a raw q above 1 is set
to 1 and ``clamped`` is true; T, tau and mu are never scaled. A factor on a member of
an applied CCF group applies to every member of the group (one group factor), and the
rows say so (``groupId``, ``viaGroup``).

Every expected number is a hand calculation (the derivation is in the comment of the
case); none comes from running F4 code. Until the route exists each test fails on
the 404 of ``POST /api/whatif`` and on nothing else.
"""
import pytest

import whatif_support as W

REL = 1e-9

#: (event, model, paramKey, nominalParam, f, param, nominalQ, q, clamped)
#:
#: rate, lambda 1e-5 /h, T 1000 h.  nominal q = 1 - exp(-1e-5 * 1000) = 1 - exp(-0.01)
#:   = 0.009950166250831947.  f = 10: lambda 1e-4, q = 1 - exp(-0.1) = 0.0951625819640404
#:   (SPEC FN-55: 0.0951626).  f = 0.01: lambda 1e-7, q = 1 - exp(-1e-4) = 9.9995000166663e-5.
#:   f = 100: lambda 1e-3, q = 1 - exp(-1) = 0.6321205588285577.
#: standby, lambda 1e-4 /h, tau 100 h.  q = min(1, lambda tau / 2); nominal 1e-4 * 100 / 2 = 5e-3.
#:   f = 10: lambda 1e-3, q = 1e-3 * 100 / 2 = 0.05.  f = 100: 1e-2 * 100 / 2 = 0.5.
#:   f = 0.01: 1e-6 * 100 / 2 = 5e-5.
#: repairable, lambda 1e-3 /h, mu 0.1 /h (never scaled).  q = lambda / (lambda + mu);
#:   nominal 1e-3 / 0.101 = 1/101 = 0.009900990099009901.  f = 10: lambda 1e-2, q = 1e-2 / 0.11
#:   = 1/11 = 0.09090909090909091.  f = 100: lambda 0.1, q = 0.1 / 0.2 = 0.5.
#:   f = 0.01: lambda 1e-5, q = 1e-5 / 0.10001 = 9.999000099990002e-05.
#: fixed q = 0.5 (the main parameter is q itself).  f = 10: 5, q = min(1, 5) = 1, clamped.
#:   f = 2: exactly 1, which is not above 1: q = 1, not clamped.  f = 0.01: 0.005.  f = 0.5: 0.25.
SCALING = [
    ("RATE", "rate", "lambda", 1e-5, 10, 1e-4, 0.009950166250831947, 0.0951625819640404, False),
    ("RATE", "rate", "lambda", 1e-5, 0.01, 1e-7, 0.009950166250831947, 9.9995000166663e-05, False),
    ("RATE", "rate", "lambda", 1e-5, 100, 1e-3, 0.009950166250831947, 0.6321205588285577, False),
    ("STBY", "standby", "lambda", 1e-4, 10, 1e-3, 5e-3, 0.05, False),
    ("STBY", "standby", "lambda", 1e-4, 100, 1e-2, 5e-3, 0.5, False),
    ("STBY", "standby", "lambda", 1e-4, 0.01, 1e-6, 5e-3, 5e-5, False),
    ("REPA", "repairable", "lambda", 1e-3, 10, 1e-2, 0.009900990099009901, 0.09090909090909091, False),
    ("REPA", "repairable", "lambda", 1e-3, 100, 0.1, 0.009900990099009901, 0.5, False),
    ("REPA", "repairable", "lambda", 1e-3, 0.01, 1e-5, 0.009900990099009901, 9.999000099990002e-05, False),
    ("FIX", "fixed", "q", 0.5, 10, 5.0, 0.5, 1.0, True),
    ("FIX", "fixed", "q", 0.5, 2, 1.0, 0.5, 1.0, False),
    ("FIX", "fixed", "q", 0.5, 0.01, 0.005, 0.5, 0.005, False),
    ("FIX", "fixed", "q", 0.5, 0.5, 0.25, 0.5, 0.25, False),
]


@pytest.mark.parametrize("event, model, key, nominal, f, param, nominal_q, q, clamped", SCALING,
                         ids=["%s-f%g" % (c[0], c[4]) for c in SCALING])
def test_the_main_parameter_is_scaled_and_q_follows_from_the_model(
        models, event, model, key, nominal, f, param, nominal_q, q, clamped):
    body = models.whatif_ok({event: f})
    row = W.row_of(body, event)
    assert row["model"] == model
    assert row["paramKey"] == key
    assert row["nominalParam"] == W.rel(nominal, REL)
    assert row["param"] == W.rel(param, REL)
    assert row["nominalQ"] == W.rel(nominal_q, REL)
    assert row["q"] == W.rel(q, REL)
    assert row["clamped"] is clamped
    assert row["factor"] == f
    assert row["evaluable"] is True
    assert row["groupId"] is None and row["viaGroup"] is False
    assert [r["id"] for r in body["events"]] == [event]


def test_rate_lambda_1e_5_t_1000_f_10_gives_q_0_0951626_to_the_spec_tolerance(models):
    """SPEC FN-55 / BRIEF 4: q = 1 - exp(-0.1) = 0.0951626, relative 1e-6."""
    row = W.row_of(models.whatif_ok({"RATE": 10}), "RATE")
    assert row["q"] == W.rel(0.0951626, 1e-6)
    assert row["nominalQ"] == W.rel(0.00995017, 1e-6)


def test_the_row_carries_the_event_name(models):
    row = W.row_of(models.whatif_ok({"RATE": 10}), "RATE")
    assert row["name"] == "Rate event"


def test_fixed_q_0_5_f_10_is_clamped_to_1_with_the_flag(models):
    """BRIEF 4: fixed q = 0.5, f = 10 gives q = 1 with the clamp flag; the main parameter is 5."""
    row = W.row_of(models.whatif_ok({"FIX": 10}), "FIX")
    assert row["q"] == 1.0 and row["clamped"] is True
    assert row["param"] == W.rel(5.0, REL)


def test_a_clamped_q_is_the_q_the_top_event_uses(models):
    """FIX at q = 1 makes the OR of the tree 1 - (1 - 1) * ... = 1.0 exactly."""
    body = models.whatif_ok({"FIX": 10})
    assert body["method"] == "treeWalk"
    assert body["whatIf"] == 1.0


def test_standby_above_one_is_clamped(api):
    """lambda 1e-3, tau 1000: nominal 0.5; f = 10: 1e-2 * 1000 / 2 = 5 > 1 -> q 1, clamped."""
    api.open_doc(W.standby_clamp_doc())
    row = W.row_of(api.whatif_ok({"SBY": 10}), "SBY")
    assert row["nominalQ"] == W.rel(0.5, REL)
    assert row["nominalParam"] == W.rel(1e-3, REL)
    assert row["param"] == W.rel(1e-2, REL)
    assert row["q"] == 1.0 and row["clamped"] is True
    unchanged = W.row_of(api.whatif_ok({"SBY": 1}), "SBY")
    assert unchanged["q"] == W.rel(0.5, REL) and unchanged["clamped"] is False


#: (id, quant, f, nominalParam, param, nominalQ, q, clamped): one event E (plus a fixed OTH).
SINGLE = [
    # standby lambda 1e-2, tau 1000: nominal lambda tau / 2 = 5, so nominalQ is capped to 1.
    # f = 0.1: lambda 1e-3, raw q 1e-3 * 1000 / 2 = 0.5.  Scaling the capped q (1 * 0.1) would
    # give 0.1: this is the one input where "scale q" and "scale lambda" differ for a standby.
    ("standby-nominal-capped", W.standby(1e-2, 1000.0), 0.1, 1e-2, 1e-3, 1.0, 0.5, False),
    # standby lambda 1e-3, tau 1000: f = 2 gives 2e-3 * 1000 / 2 = 1 exactly: q 1, not clamped
    # (DESIGN 4.1: clamped only when the raw q is strictly above 1).
    ("standby-exactly-one", W.standby(1e-3, 1000.0), 2, 1e-3, 2e-3, 0.5, 1.0, False),
    # rate without T: the mission time of the document, 8760 h (SPEC): nominal 1 - exp(-0.0876)
    # = 0.08387274565534581; f = 10: 1 - exp(-0.876) = 0.5835546339796199.
    ("rate-mission-time", {"model": "rate", "lambda": 1e-5}, 10, 1e-5, 1e-4,
     0.08387274565534581, 0.5835546339796199, False),
    # repairable with a repair time only: mu = 1 / mttr = 0.1; f = 10: 1e-2 / (1e-2 + 0.1) = 1/11.
    ("repairable-mttr", {"model": "repairable", "lambda": 1e-3, "mttr": 10.0}, 10, 1e-3, 1e-2,
     1.0 / 101.0, 1.0 / 11.0, False),
    # rate lambda 1, T 1000, f = 10: 1 - exp(-10000) is 1.0, but it is never above 1: not clamped.
    ("rate-saturated", W.rate(1.0, 1000.0), 10, 1.0, 10.0, 1.0, 1.0, False),
    # lambda 1e-13, T 1000, f = 0.01: lambda T = 1e-12, q = 1 - exp(-1e-12) = 9.999999999995e-13
    # (1e-12 - 5e-25).  Nominal: lambda T = 1e-10, q = 9.9999999995e-11.  The naive 1 - exp(-x)
    # loses digits there and gives 9.99978e-13.
    ("rate-tiny-lambda", W.rate(1e-13, 1000.0), 0.01, 1e-13, 1e-15, 9.9999999995e-11,
     9.999999999995e-13, False),
]


@pytest.mark.parametrize("quant, f, nominal, param, nominal_q, q, clamped",
                         [c[1:] for c in SINGLE], ids=[c[0] for c in SINGLE])
def test_edge_cases_of_the_models(api, quant, f, nominal, param, nominal_q, q, clamped):
    api.open_doc(W.single_event_doc(quant))
    row = W.row_of(api.whatif_ok({"E": f}), "E")
    assert row["nominalParam"] == W.rel(nominal, REL)
    assert row["param"] == W.rel(param, REL)
    assert row["nominalQ"] == W.rel(nominal_q, REL)
    assert row["q"] == W.rel(q, REL)
    assert row["clamped"] is clamped
    assert row["evaluable"] is True


def test_standby_exactly_one_is_exactly_one(api):
    api.open_doc(W.single_event_doc(W.standby(1e-3, 1000.0)))
    row = W.row_of(api.whatif_ok({"E": 2}), "E")
    assert row["q"] == 1.0 and row["clamped"] is False


@pytest.mark.parametrize("f", [0.01, 100, 100.0, 1, 1.0, 0.5, 1.122])
def test_the_bounds_and_inside_values_are_accepted(models, f):
    for event in ("RATE", "STBY", "REPA", "FIX"):
        body = models.whatif_ok({event: f})
        assert W.row_of(body, event)["factor"] == f


def test_a_factor_of_1_changes_nothing_and_the_row_shows_the_nominal_numbers(models):
    body = models.whatif_ok({"RATE": 1})
    row = W.row_of(body, "RATE")
    assert row["factor"] == 1
    assert row["param"] == W.rel(row["nominalParam"], 1e-12)
    assert row["q"] == W.rel(row["nominalQ"], 1e-12)
    assert row["clamped"] is False
    assert body["whatIf"] == body["baseline"]


def test_the_integer_and_the_float_spelling_of_a_factor_give_the_same_answer(models):
    first = models.whatif_ok({"RATE": 10})
    second = models.whatif_ok({"RATE": 10.0})
    assert first["whatIf"] == second["whatIf"]
    assert W.row_of(first, "RATE")["q"] == W.row_of(second, "RATE")["q"]


def test_several_events_keep_the_request_order_and_all_count_in_the_top_event(models):
    # written as text: the test client's json= sorts the keys, a browser keeps insertion order
    status, body = models.raw_with('{"STBY": 10, "RATE": 10, "FIX": 1}')
    assert status == 200, body
    assert [r["id"] for r in body["events"]] == ["STBY", "RATE", "FIX"]
    # OR[RATE, STBY, REPA, FIX] with RATE 0.0951625819640404, STBY 0.05, REPA 1/101, FIX 0.5:
    # 1 - (1 - 0.0951625819640404)(1 - 0.05)(1 - 1/101)(1 - 0.5) = 0.5744576499335834 (hand product).
    assert body["whatIf"] == W.rel(0.5744576499335834, REL)


# --------------------------------------------------------------- CCF members


GROUP_ROW_KEYS = {"id", "name", "model", "members"}


def test_f_10_on_member_a_of_r1_scales_both_members(r1):
    """R1: Q_t 1e-3, f = 10 -> Q_t 1e-2 for A and for B (the rows show the total Q_t, not
    the independent part 9e-3); both carry the group id; B is there because of the group."""
    body = r1.whatif_ok({"A": 10})
    assert [r["id"] for r in body["events"]] == ["A", "B"]
    a, b = body["events"]
    for row in (a, b):
        assert row["model"] == "fixed" and row["paramKey"] == "q"
        assert row["nominalParam"] == W.rel(1e-3, REL)
        assert row["param"] == W.rel(1e-2, REL)
        assert row["nominalQ"] == W.rel(1e-3, REL)
        assert row["q"] == W.rel(1e-2, REL)
        assert row["clamped"] is False
        assert row["factor"] == 10
        assert row["groupId"] == "g1"
        assert row["evaluable"] is True
    assert a["viaGroup"] is False and b["viaGroup"] is True
    assert body["groups"] and {k: body["groups"][0][k] for k in GROUP_ROW_KEYS} == {
        "id": "g1", "name": W.M.GROUP_NAME, "model": "beta", "members": ["A", "B"]}


def test_f_10_on_member_b_lists_b_first_then_the_other_members_in_group_order(r1):
    body = r1.whatif_ok({"B": 10})
    assert [r["id"] for r in body["events"]] == ["B", "A"]
    assert body["events"][0]["viaGroup"] is False and body["events"][1]["viaGroup"] is True
    assert body["whatIf"] == W.rel(W.R1_F10, REL)  # the same as a factor on A


def test_a_member_with_factor_1_next_to_a_member_with_10_means_a_group_factor_of_10(r1):
    alone = r1.whatif_ok({"A": 10})
    mixed = r1.whatif_ok({"A": 10, "B": 1})
    assert mixed["whatIf"] == alone["whatIf"]
    for row in mixed["events"]:
        assert row["q"] == W.rel(1e-2, REL)


def test_equal_factors_on_both_members_are_one_group_factor(r1):
    both = r1.whatif_ok({"A": 10, "B": 10})
    assert both["whatIf"] == W.rel(W.R1_F10, REL)
    assert {r["id"] for r in both["events"]} == {"A", "B"}


def test_two_members_with_different_factors_are_a_group_conflict(r1):
    before = W.fingerprint()
    err = W.assert_error(r1.whatif({"A": 10, "B": 5}), 400, "INVALID_FIELD", field="factors",
                         reason="group_conflict", groupId="g1")
    assert sorted(err["detail"]["ids"]) == ["A", "B"]
    W.assert_error(r1.whatif({"B": 5, "A": 10}), 400, "INVALID_FIELD", field="factors",
                   reason="group_conflict", groupId="g1")
    assert W.fingerprint() == before


def test_a_factor_on_a_member_with_f_1_only_does_not_pull_in_the_group(r1):
    body = r1.whatif_ok({"B": 1})
    assert [r["id"] for r in body["events"]] == ["B"]
    assert body["events"][0]["viaGroup"] is False
    assert body["whatIf"] == body["baseline"]


def test_a_non_member_with_q_0_has_the_nominal_q_and_leaves_the_top_event_alone(r1):
    """C is 0 in R1 and 10 * 0 = 0: the changed q equals the nominal q, so the what-if is the
    baseline object itself (DESIGN 3.2: the same float)."""
    body = r1.whatif_ok({"C": 10})
    row = W.row_of(body, "C")
    assert row["groupId"] is None and row["q"] == 0 and row["nominalQ"] == 0
    assert body["whatIf"] == body["baseline"]


def test_a_group_of_rate_members_scales_lambda_then_splits_q_t_by_the_beta_model(api):
    """A, B rate, lambda 1e-5 /h, T 1000 h, beta 0.1, under an AND.

    f = 10: lambda 1e-4 for both, Q_t = 1 - exp(-0.1) = 0.09516258196404043 (each row);
    CCF event beta Q_t = 0.009516258196404043; independent (1 - beta) Q_t = 0.08564632376763638,
    set {A', B'} = 0.08564632376763638^2 = 0.007335292774910797.
    MCUB = 1 - (1 - 0.009516258196404043)(1 - 0.007335292774910797) = 0.01678174643132257.
    Baseline (Q_t 0.009950166250831947): CCF 9.950166250831947e-4, set 8.019470481954802e-05,
    MCUB 0.0010751315348382036."""
    api.open_doc(W.rate_group_doc())
    body = api.whatif_ok({"A": 10})
    assert body["method"] == "mcub"
    assert body["baseline"] == W.rel(0.0010751315348382036, REL)
    assert body["whatIf"] == W.rel(0.01678174643132257, REL)
    for row in body["events"]:
        assert row["paramKey"] == "lambda"
        assert row["nominalParam"] == W.rel(1e-5, REL)
        assert row["param"] == W.rel(1e-4, REL)
        assert row["nominalQ"] == W.rel(0.009950166250831947, REL)
        assert row["q"] == W.rel(0.09516258196404043, REL)
        assert row["groupId"] == "g1"
    assert [r["viaGroup"] for r in body["events"]] == [False, True]


def test_the_clamp_comes_before_the_beta_split_for_a_group(api):
    """R1 shape, A and B fixed 0.5, beta 0.1, AND.  Baseline: CCF event 0.05, independent 0.45,
    set 0.2025: 1 - (1 - 0.05)(1 - 0.2025) = 0.242375.
    f = 10 on A: Q_t = min(1, 5) = 1 for both rows, then the split: CCF event 0.1, independent
    0.9, set 0.81: 1 - (1 - 0.1)(1 - 0.81) = 1 - 0.9 * 0.19 = 0.829.  A build that splits the
    unclamped 5 first, or does not clamp the member, gives another number."""
    api.open_doc(W.group_doc(0.5))
    body = api.whatif_ok({"A": 10})
    assert body["method"] == "mcub"
    assert body["baseline"] == W.rel(0.242375, REL)
    assert body["whatIf"] == W.rel(0.829, REL)
    assert [r["id"] for r in body["events"]] == ["A", "B"]
    for row in body["events"]:
        assert row["q"] == 1.0 and row["clamped"] is True
        assert row["param"] == W.rel(5.0, REL)
        assert row["nominalQ"] == W.rel(0.5, REL)
        assert row["groupId"] == "g1"


def test_members_of_a_group_that_is_not_applied_are_ordinary_events(api):
    """B has q 2e-3, A 1e-3: FN-33 does not apply the group, so there is no group factor.

    {A: 10, B: 5} is accepted: A 1e-2, B 2e-3 * 5 = 1e-2, AND = 1e-4 (tree walk, OR with C = 0).
    Baseline 1e-3 * 2e-3 = 2e-6."""
    api.open_doc(W.unapplied_group_doc())
    body = api.whatif_ok({"A": 10, "B": 5})
    assert body["groups"] == []
    assert [r["id"] for r in body["events"]] == ["A", "B"]
    assert all(r["groupId"] is None and r["viaGroup"] is False for r in body["events"])
    assert body["method"] == "treeWalk"
    assert body["baseline"] == W.rel(2e-6, REL)
    assert body["whatIf"] == W.rel(1e-4, REL)


def test_groups_is_always_present_and_empty_when_no_group_applies(models):
    body = models.whatif_ok({"RATE": 10})
    assert body["groups"] == []


# ------------------------------------------- standby: the clamp at the edges (T1 round 1)


def test_standby_with_a_raw_q_above_one_at_factor_1_is_clamped(api):
    """lambda 1e-2, tau 1000: lambda tau / 2 = 5 > 1 already at the nominal value, so f = 1
    gives q 1 and ``clamped`` true (DESIGN 3.2: true iff the unclamped q is above 1). The
    unfixed build said false at f = 1 and true at f = 1.0001."""
    api.open_doc(W.single_event_doc(W.standby(1e-2, 1000.0)))
    for f in (1, 1.0, 1.0001):
        body = api.whatif_ok({"E": f})
        row = W.row_of(body, "E")
        assert row["q"] == 1.0 and row["nominalQ"] == 1.0
        assert row["clamped"] is True, f
        assert row["param"] == W.rel(1e-2 * f, REL)


def test_standby_with_a_raw_q_of_exactly_one_at_factor_1_is_not_clamped(api):
    """lambda 2e-3, tau 1000: lambda tau / 2 = 1 exactly, which is not above 1."""
    api.open_doc(W.single_event_doc(W.standby(2e-3, 1000.0)))
    for f in (1, 1.0):
        row = W.row_of(api.whatif_ok({"E": f}), "E")
        assert row["q"] == 1.0 and row["clamped"] is False


def test_standby_with_a_raw_q_just_above_one_is_clamped(api):
    """lambda 1.0000000000004e-3, tau 1000, f = 2: lambda tau / 2 = 1.0000000000004001, which
    is above 1 although the engine's 12-digit rounding would make it 1.0: ``clamped`` is true
    (DESIGN 3.2: true iff the unclamped q is above 1). The other side of the exact-one test."""
    api.open_doc(W.single_event_doc(W.standby(1.0000000000004e-3, 1000.0)))
    row = W.row_of(api.whatif_ok({"E": 2}), "E")
    assert row["q"] == 1.0 and row["clamped"] is True


@pytest.mark.parametrize("f", [0.01, 100])
def test_standby_whose_raw_q_overflows_is_clamped_and_not_refused(api, f):
    """lambda 1e300, tau 1e20: the scaled lambda (1e298 or 1e302) is finite, lambda tau / 2
    overflows to infinity, which is above 1: q 1, ``clamped`` true, HTTP 200 (DESIGN 4.3, Rev 5 rider 3).
    The unfixed build answered 422 WHATIF_NOT_EVALUABLE."""
    api.open_doc(W.single_event_doc(W.standby(1e300, 1e20)))
    status, body = api.whatif({"E": f})
    assert status == 200, body
    row = W.row_of(body, "E")
    assert row["q"] == 1.0 and row["clamped"] is True
    assert row["param"] == W.rel(f * 1e300, REL)
    assert row["evaluable"] is True


def test_a_scaled_parameter_that_is_not_finite_is_refused_but_a_finite_one_is_not(api):
    """lambda 1e308, tau 1e20: f = 100 gives lambda 1e310 = infinity, which cannot be shown
    (JSON has no infinity): 422 WHATIF_NOT_EVALUABLE. f = 0.01 on the same event is 200."""
    api.open_doc(W.single_event_doc(W.standby(1e308, 1e20)))
    W.assert_error(api.whatif({"E": 100}), 422, "WHATIF_NOT_EVALUABLE", id="E", missing=[])
    row = W.row_of(api.whatif_ok({"E": 0.01}), "E")
    assert row["q"] == 1.0 and row["clamped"] is True
