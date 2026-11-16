"""F4 BRIEF criterion 5 (FN-56): the what-if top event uses the headline's method.

* MCUB headline (always with an applied CCF group, also with repeated events): the
  MCUB over the baseline's cut sets with the changed q values (``mcub_of``);
* tree-walk headline: the tree walk of the tree with the changed q values;
* ``incomplete`` headline: no number, ``baseline`` / ``whatIf`` / ``ratio`` are null,
  ``note`` is ``"incomplete"``;
* the cut sets were cut short by the document's cutoff: ``note`` is
  ``"cutsets_from_nominal"`` and the number is computed from the nominal cut sets; an order
  cut or a tree-walk headline gives no note (DESIGN 3.2);
* ``ratio`` is null when the baseline is 0 and the what-if is above 0, and when the quotient
  is not a finite number (the response must stay strict JSON).

R1 (SPEC 7.4): A, B fixed 1e-3, AND, beta group beta = 0.1, Q_t = 1e-3.
  baseline: CCF event 1e-4, set {A', B'} (9e-4)^2 = 8.1e-7, MCUB = 1 - (1 - 1e-4)(1 - 8.1e-7)
            = 1.00809919e-4.
  f = 10 on A: Q_t 1e-2 for both; CCF event 1e-3; independent 9e-3 each, set 8.1e-5;
            MCUB = 1 - (1 - 1e-3)(1 - 8.1e-5) = 1e-3 + 8.1e-5 - 8.1e-8 = 1.080919e-3.
  f = 0.1 on A: Q_t 1e-4; CCF 1e-5; independent 9e-5, set 8.1e-9;
            MCUB = 1 - (1 - 1e-5)(1 - 8.1e-9) = 1.0008099919e-5.

Every number is compared with ``W.rel`` (a purely relative tolerance, ``abs=0``).
"""
import json
import math

import pytest

import whatif_support as W

REL = 1e-9

MODELS_BASELINE = W.MODELS_BASELINE
MODELS_RATE_10 = W.MODELS_RATE_10
MODELS_STBY_10 = W.MODELS_STBY_10
MODELS_REPA_10 = W.MODELS_REPA_10
MODELS_FIX_001 = W.MODELS_FIX_001


# ------------------------------------------------------------------ MCUB, R1


def test_r1_factor_1_gives_the_headline_exactly(r1):
    headline = r1.headline()
    assert headline == W.rel(W.R1_BASELINE, REL)
    for factors in ({}, {"A": 1}, {"A": 1, "B": 1}, {"C": 1}):
        body = r1.whatif_ok(factors)
        assert body["baseline"] == headline        # the same float
        assert body["whatIf"] == body["baseline"]  # == , not approx
        assert body["ratio"] == 1.0
        assert body["method"] == "mcub"
        assert body["note"] is None
        assert body["truncatedBy"] == []


def test_r1_factor_10_on_a_gives_1_080919e_3(r1):
    body = r1.whatif_ok({"A": 10})
    assert body["method"] == "mcub"
    assert body["baseline"] == W.rel(W.R1_BASELINE, REL)
    assert body["whatIf"] == W.rel(W.R1_F10, REL)
    assert body["ratio"] == W.rel(W.R1_F10_RATIO, 1e-6)
    assert body["ratio"] == W.absolute(10.72, 0.005)
    assert body["note"] is None


def test_r1_factor_0_1_on_a(r1):
    body = r1.whatif_ok({"A": 0.1})
    assert body["whatIf"] == W.rel(1.0008099919e-5, REL)
    assert body["ratio"] == W.rel(0.09927693641932198, 1e-6)


def test_the_response_has_the_documented_top_level_shape(r1):
    body = r1.whatif_ok({"A": 10})
    fields = r1.fields()
    assert body["ok"] is True
    assert body["revision"] == fields["revision"] and body["documentSerial"] == fields["documentSerial"]
    for key in ("baseline", "whatIf", "ratio", "method", "note", "truncatedBy", "cache",
                "baselineMs", "groups", "events"):
        assert key in body, key
    assert isinstance(body["events"], list) and isinstance(body["groups"], list)


def test_the_baseline_is_the_float_of_the_summary_endpoint(r1):
    summary = r1.summary()
    body = r1.whatif_ok({"A": 10})
    assert summary["headlineMethod"] == body["method"] == "mcub"
    assert body["baseline"] == summary["headline"]


def test_the_r1_what_if_is_mcub_of_the_two_cut_set_probabilities(r1):
    """Tied to the function the headline uses (DESIGN D3): the cut sets of f = 10 are the CCF
    event 1e-3 and the independent set (9e-3)^2 = 8.1e-5, and the number is ``mcub_of`` of them."""
    from fta_web import cutsets

    body = r1.whatif_ok({"A": 10})
    assert body["whatIf"] == W.rel(cutsets.mcub_of([1e-3, 8.1e-5]), 1e-12)


def test_the_r1_what_if_equals_the_headline_of_the_same_document_edited_by_hand(r1):
    """A and B typed in as 1e-2 (the group's Q_t after the factor), run through the existing
    engine: the headline of that document is the what-if number, to 1e-12."""
    hand = W.hand_headline(W.r1_doc(), {"A", "B"}, 1e-2)
    assert hand["headlineMethod"] == "mcub"
    assert r1.whatif_ok({"A": 10})["whatIf"] == W.rel(hand["headline"], 1e-12)


def test_small_probabilities_keep_their_digits_in_the_union_form(api):
    """R1 shape with q 1e-12 and cutoff 1e-30, f = 0.01 on A: Q_t 1e-14, CCF event 1e-15,
    independent 9e-15 each, set 8.1e-29; baseline 1e-13 + 8.1e-25 (both sets kept).
    1 - (1 - 1e-15)(1 - 8.1e-29) = 1e-15 + 8.1e-29 to 1e-9; the product form 1 - prod(1 - p)
    cancels to 9.992e-16 in floating point."""
    api.open_doc(W.small_group_doc())
    body = api.whatif_ok({"A": 0.01})
    assert body["method"] == "mcub"
    assert body["baseline"] == W.rel(1e-13 + 8.1e-25, REL)
    assert body["whatIf"] == W.rel(1e-15 + 8.1e-29, REL)


def test_a_repeated_event_without_a_group_is_mcub_and_not_the_tree_walk(api):
    """AND[OR[A, B], OR[X, C]] where X (q 0) has an OR link to A, A 0.01, B = C = 0.1: cut sets
    {A}, {B, X} (0) and {B, C}.
    Baseline 1 - (1 - 0.01)(1 - 0.01) = 0.0199 (the tree walk, 0.011881, counts A twice).
    f = 10 on A: A 0.1: 1 - (1 - 0.1)(1 - 0.01) = 0.109."""
    api.open_doc(W.repeated_doc())
    body = api.whatif_ok({"A": 10})
    assert body["method"] == "mcub"
    assert body["baseline"] == W.rel(0.0199, REL)
    assert body["whatIf"] == W.rel(0.109, REL)
    assert body["ratio"] == W.rel(0.109 / 0.0199, 1e-6)
    assert body["note"] is None
    assert [r["id"] for r in body["events"]] == ["A"]


def test_the_clamp_holds_in_a_multi_event_cut_set(api):
    """Same document, f = 20 on B (q 0.1): the raw q is 2, the row says q 1 and clamped. The cut
    set {B, C} is then 1 * 0.1 = 0.1 and 1 - (1 - 0.01)(1 - 0.1) = 0.109. A build that multiplies
    the unclamped 2 into the set gets {B, C} = 0.2 and 0.208."""
    api.open_doc(W.repeated_doc())
    body = api.whatif_ok({"B": 20})
    row = W.row_of(body, "B")
    assert row["nominalQ"] == W.rel(0.1, REL)
    assert row["param"] == W.rel(2.0, REL)
    assert row["q"] == 1.0 and row["clamped"] is True
    assert body["method"] == "mcub"
    assert body["whatIf"] == W.rel(0.109, REL)


def test_a_group_factor_and_an_independent_factor_together_in_either_order(api):
    """R1 plus P (rate, lambda 1e-5 /h, T 1000 h). f = 10 on A: CCF event 1e-3, independent set
    8.1e-5; P at 0.5: lambda 5e-6, q = 1 - exp(-0.005) = 0.004987520807317687.
    MCUB = 1 - (1 - 1e-3)(1 - 8.1e-5)(1 - 0.004987520807317687) = 0.006063048701314162.
    The request order does not matter (written as text: json= sorts the keys)."""
    api.open_doc(W.group_and_rate_doc())
    for text in ('{"P": 0.5, "A": 10}', '{"A": 10, "P": 0.5}'):
        status, body = api.raw_with(text)
        assert status == 200, body
        assert body["method"] == "mcub"
        assert body["whatIf"] == W.rel(0.006063048701314162, REL), text
        assert W.row_of(body, "P")["q"] == W.rel(0.004987520807317687, REL)
        assert {r["id"] for r in body["events"]} == {"P", "A", "B"}


def test_two_groups_are_both_scaled(api):
    """g1 (A, B) and g2 "Valves" (D, E), beta 0.1, all q 1e-3, under two ANDs; {A: 10, D: 0.1}.
    g1: CCF event 1e-3, independent set (9e-3)^2 = 8.1e-5.  g2: Q_t 1e-4, CCF event 1e-5,
    independent set (9e-5)^2 = 8.1e-9.
    MCUB = 1 - (1 - 1e-3)(1 - 8.1e-5)(1 - 1e-5)(1 - 8.1e-9) = 1.0909162819736437e-3.
    A build that drops the factor of the second group keeps D, E at 1e-3 (CCF event 1e-4,
    set 8.1e-7) and gives about 1.18e-3."""
    api.open_doc(W.two_groups_doc())
    for text in ('{"A": 10, "D": 0.1}', '{"D": 0.1, "A": 10}'):
        status, body = api.raw_with(text)
        assert status == 200, body
        assert [g["id"] for g in body["groups"]] == ["g1", "g2"]
        assert body["whatIf"] == W.rel(1.0909162819736437e-3, REL), text
        assert W.row_of(body, "D")["q"] == W.rel(1e-4, REL)
        assert W.row_of(body, "E")["viaGroup"] is True
        assert W.row_of(body, "B")["groupId"] == "g1" and W.row_of(body, "E")["groupId"] == "g2"


# ----------------------------------------------------- cut sets from nominal


def test_cutoff_dropped_cut_sets_stay_dropped_and_the_note_says_so(api):
    """cutoff 1e-6 drops the independent set (8.1e-7). Baseline = the CCF set alone = 1e-4.
    f = 10 on A: the CCF event is 1e-3, the dropped set is not brought back: whatIf = 1e-3,
    not 1.080919e-3."""
    api.open_doc(W.r1_cutoff_doc())
    body = api.whatif_ok({"A": 10})
    assert body["method"] == "mcub"
    assert "cutoff" in body["truncatedBy"]
    assert body["baseline"] == W.rel(1e-4, REL)
    assert body["whatIf"] == W.rel(1e-3, REL)
    assert body["ratio"] == W.rel(10.0, 1e-6)
    assert body["note"] == "cutsets_from_nominal"


def test_the_cutoff_note_is_there_without_a_factor_too(api):
    api.open_doc(W.r1_cutoff_doc())
    body = api.whatif_ok({})
    assert body["note"] == "cutsets_from_nominal"
    assert body["whatIf"] == body["baseline"]
    assert body["baseline"] == W.rel(1e-4, REL)


def test_no_cutoff_no_note(api):
    api.open_doc(W.r1_cutoff_doc(cutoff=1e-9))  # below every set: nothing is dropped
    body = api.whatif_ok({"A": 10})
    assert body["note"] is None
    assert "cutoff" not in body["truncatedBy"]
    assert body["whatIf"] == W.rel(W.R1_F10, REL)


def test_an_order_cut_alone_gives_no_note(api):
    """maxOrder 1 drops the order-2 set {A', B'}: ``truncatedBy`` says order, but only a cutoff
    earns the note (DESIGN 3.2: order and count truncation are not noted).
    Baseline 1e-4 (the CCF event); f = 10: 1e-3."""
    api.open_doc(W.r1_analysis_doc(maxOrder=1))
    body = api.whatif_ok({"A": 10})
    assert body["method"] == "mcub"
    assert "order" in body["truncatedBy"] and "cutoff" not in body["truncatedBy"]
    assert body["note"] is None
    assert body["baseline"] == W.rel(1e-4, REL)
    assert body["whatIf"] == W.rel(1e-3, REL)


def test_a_cutoff_on_a_tree_walk_headline_gives_no_note(api):
    """models_doc with cutoff 0.1: the headline is still the tree walk (no group, no repeated
    event) and ``truncatedBy`` has cutoff, but the note is only for an MCUB headline: the tree
    walk does not use the cut sets, so the what-if number is the full one."""
    api.open_doc(W.models_doc(analysis={"cutsets": {"cutoff": 0.1}}))
    body = api.whatif_ok({"RATE": 10})
    assert body["method"] == "treeWalk"
    assert "cutoff" in body["truncatedBy"]
    assert body["note"] is None
    assert body["whatIf"] == W.rel(MODELS_RATE_10, REL)


# ---------------------------------------------------------------- incomplete


def test_an_incomplete_headline_has_no_number_and_a_note(api, monkeypatch):
    """The summary's own cut-set cap (SUMMARY_LIMITS maxCount 1) cuts the R1 cut sets short:
    with an applied group the headline is then ``incomplete`` (FN-21) and so is the what-if."""
    from fta_web import engine

    monkeypatch.setitem(engine.SUMMARY_LIMITS, "maxCount", 1)
    api.open_doc(W.r1_doc())
    assert api.summary()["headlineMethod"] == "incomplete"  # the premise
    body = api.whatif_ok({"A": 10})
    assert body["method"] == "incomplete"
    assert body["baseline"] is None and body["whatIf"] is None and body["ratio"] is None
    assert body["note"] == "incomplete"
    # the rows are still there (DESIGN 4.3)
    assert [r["id"] for r in body["events"]] == ["A", "B"]
    assert W.row_of(body, "A")["q"] == W.rel(1e-2, REL)


def test_an_incomplete_headline_with_no_factor_is_still_null(api, monkeypatch):
    from fta_web import engine

    monkeypatch.setitem(engine.SUMMARY_LIMITS, "maxCount", 1)
    api.open_doc(W.r1_doc())
    body = api.whatif_ok({})
    assert body["method"] == "incomplete" and body["whatIf"] is None and body["baseline"] is None
    assert body["note"] == "incomplete"


# ----------------------------------------------------------------- tree walk


def test_a_tree_without_repeated_events_or_groups_uses_the_tree_walk(models):
    body = models.whatif_ok({})
    assert body["method"] == "treeWalk"
    assert body["note"] is None
    assert body["baseline"] == W.rel(MODELS_BASELINE, REL)
    assert body["whatIf"] == body["baseline"]


@pytest.mark.parametrize("factors, expected", [
    ({"RATE": 10}, MODELS_RATE_10),
    ({"STBY": 10}, MODELS_STBY_10),
    ({"REPA": 10}, MODELS_REPA_10),
    ({"FIX": 0.01}, MODELS_FIX_001),
    ({"FIX": 10}, 1.0),
], ids=["rate", "standby", "repairable", "fixed-down", "fixed-clamped"])
def test_the_tree_walk_what_if_is_the_product_form_of_the_changed_q_values(models, factors, expected):
    """OR[RATE, STBY, REPA, FIX] = 1 - prod(1 - q): the literals are that product with the one
    changed q (rate 0.0951625819640404, standby 0.05, repairable 1/11, fixed 0.005, fixed 1)."""
    body = models.whatif_ok(factors)
    assert body["method"] == "treeWalk"
    assert body["whatIf"] == W.rel(expected, REL)
    assert body["ratio"] == W.rel(expected / MODELS_BASELINE, 1e-6)


def test_the_tree_walk_what_if_equals_the_tree_walk_of_the_same_tree_edited_by_hand(models):
    """The same tree with RATE's lambda typed as 1e-4 and FIX's probability typed as 0.005,
    run through the existing engine, gives the what-if of {RATE: 10, FIX: 0.01}."""
    from fta_web import engine

    tree = W.models_tree()
    for node in tree["children"]:
        if node["id"] == "RATE":
            node["quant"]["lambda"] = 1e-4
        if node["id"] == "FIX":
            node["probability"] = 0.005
    hand = engine.summary(tree, None)
    assert hand["headlineMethod"] == "treeWalk"
    body = models.whatif_ok({"RATE": 10, "FIX": 0.01})
    assert body["whatIf"] == W.rel(hand["headline"], 1e-12)


def test_the_tree_walk_is_not_the_mcub_of_the_same_tree(api):
    """AND[OR[A, B], OR[C, D]], all fixed 0.1; f = 5 on A (q 0.5).

    Tree walk: OR1 = 1 - 0.5 * 0.9 = 0.55, OR2 = 1 - 0.9 * 0.9 = 0.19, AND = 0.55 * 0.19 = 0.1045
    (baseline 0.19 * 0.19 = 0.0361). The MCUB of the four cut sets {A,C} {A,D} {B,C} {B,D}
    (0.05, 0.05, 0.01, 0.01) is 1 - 0.95^2 * 0.99^2 = 0.11545975: a build that uses the MCUB for
    a tree-walk headline gives that number. A single OR cannot tell them apart."""
    api.open_doc(W.and_of_ors_doc())
    body = api.whatif_ok({"A": 5})
    assert body["method"] == "treeWalk"
    assert body["baseline"] == W.rel(0.0361, REL)
    assert body["whatIf"] == W.rel(0.1045, REL)
    assert body["whatIf"] != W.rel(0.11545975, 1e-3)
    assert body["ratio"] == W.rel(0.1045 / 0.0361, 1e-6)
    assert body["note"] is None


# ---------------------------------------------------------------- baseline 0


def test_baseline_zero_and_what_if_zero_give_ratio_1(api):
    """Z and Y are fixed 0: 10 * 0 = 0, so baseline 0, what-if 0 and the ratio is 1.0."""
    api.open_doc(W.zero_doc())
    body = api.whatif_ok({"Z": 10})
    assert body["baseline"] == 0 and body["whatIf"] == 0
    assert body["ratio"] == 1.0
    assert body["method"] == "treeWalk"


def test_baseline_zero_and_what_if_above_zero_give_ratio_null(api):
    """AND[A, B] with A, B fixed 1e-162: the product 1e-324 underflows to 0, so the baseline is
    0. Factor 100 on A: 1e-160 * 1e-162 = 1e-322 (a denormal), above 0. There is no quotient:
    the ratio is null (DESIGN 3.2), not 1.0 and not infinity."""
    api.open_doc(W.underflow_doc())
    body = api.whatif_ok({"A": 100})
    assert body["method"] == "treeWalk"
    assert body["baseline"] == 0
    assert body["whatIf"] > 0
    assert body["whatIf"] == W.rel(1e-322, 1e-2)   # a denormal: about 3 significant digits
    assert body["ratio"] is None


def test_a_quotient_that_overflows_is_null_and_the_response_is_strict_json(api):
    """AND of 160 events, fixed 0.01: baseline 0.01 ** 160 = 1e-320 (a denormal above 0).
    Factor 100 on every event: each q is 1 and the top event 1.0; 1.0 / 1e-320 overflows to
    infinity, which JSON cannot hold (JSON.parse in the browser refuses it): the ratio is null
    (DESIGN 3.2, rev 4). The response is read exactly as a browser reads it."""
    api.open_doc(W.overflow_doc(160))
    factors = {"E%d" % i: 100 for i in range(160)}
    payload = api.payload(factors)
    status, raw = api.binary("POST", W.URL, json=payload)
    assert status == 200, raw[:300]

    def refuse(token):
        raise AssertionError("the response holds %s: JSON.parse would fail" % token)

    body = json.loads(raw.decode("utf-8"), parse_constant=refuse)
    assert body["method"] == "treeWalk"
    assert 0 < body["baseline"] < 1e-300
    assert body["whatIf"] == 1.0
    assert body["ratio"] is None


def test_ratio_is_what_if_over_baseline_otherwise(models):
    body = models.whatif_ok({"RATE": 10})
    assert body["ratio"] == W.rel(body["whatIf"] / body["baseline"], 1e-12)


# ------------------------------------------- the top event uses the engine's own q
#
# The engine stores every non-fixed model's q rounded to 12 significant digits
# (``engine._tidy``), and the cut sets and the tree walk of a document with the scaled
# parameter typed in use that value. A what-if that used the raw q' differed from the typed
# document from the 11th digit (T1 round 1: rel 2.6e-12 and 9.1e-12). These guards compare the
# endpoint with the headline of the typed document through the real engine at rel 1e-12.


def _typed_headline(doc, scaled):
    """``engine.summary`` of ``doc`` with ``scaled`` ({event id: factor}) typed into the
    event's main parameter (lambda): what a user who edits the parameters by hand sees."""
    import copy

    from fta_web import engine

    tree = copy.deepcopy(doc["tree"])
    for node in W.walk(tree):
        factor = scaled.get(node.get("id"))
        if factor is not None:
            node["quant"]["lambda"] = factor * node["quant"]["lambda"]
    return engine.summary(tree, doc.get("analysis"))


@pytest.mark.parametrize("factor", [2, 50])
def test_a_rate_group_what_if_equals_the_headline_of_the_document_with_lambda_typed_in(api, factor):
    """``rate_group_doc`` (A, B rate, lambda 1e-5, T 1000, beta 0.1), f on A: both members get
    lambda f * 1e-5. T1 round 1 measured 0.002297098745613824 against the typed
    0.0022970987456079244 (f = 2): rel 2.57e-12, which this tolerance (1e-12, abs 0) refuses."""
    doc = W.rate_group_doc()
    api.open_doc(doc)
    body = api.whatif_ok({"A": factor})
    typed = _typed_headline(doc, {"A": factor, "B": factor})
    assert typed["headlineMethod"] == "mcub" and body["method"] == "mcub"
    assert body["whatIf"] == W.rel(typed["headline"], 1e-12)
    if factor == 2:
        assert typed["headline"] == W.rel(0.0022970987456079244, 1e-12)
    # the top event uses the engine's rounded q, but the row keeps the raw one (DESIGN 4.3,
    # Rev 5 rider 1): tidying it changes the 12th digit (rel 2.3e-12 at f = 2, 9.3e-13 at 50)
    raw_q = -math.expm1(-factor * 1e-5 * 1000.0)
    assert W.row_of(body, "A")["q"] == W.rel(raw_q, 1e-14)
    assert W.row_of(body, "B")["q"] == W.rel(raw_q, 1e-14)


def _tree_walk_rounding_doc():
    """OR of two fixed events, two repairable events and one rate event with the mission time
    (no T): no repeated event and no group, so the headline is the tree walk. The values are
    the T1 round 1 mismatch document."""
    return W.M.document(W.M.top([
        W.M.leaf("E1", 7.191868160447103e-07, name="Fixed one"),
        W.M.leaf("E3", 8.477925316897226e-05, name="Fixed three"),
        W.M.leaf("E0", 0.0, name="Repairable zero",
                 quant=W.repairable(0.0006614274739548786, 0.05482309589202993)),
        W.M.leaf("E4", 0.0, name="Rate four",
                 quant={"model": "rate", "lambda": 2.497736362702697e-07}),
        W.M.leaf("E2", 0.0, name="Repairable two",
                 quant=W.repairable(1.8622752446259775e-05, 6.84251134500856)),
    ]), None)


def test_a_tree_walk_what_if_equals_the_headline_of_the_document_with_lambda_typed_in(api):
    """The T1 round 1 document, {E0: 10, E2: 10}: whatIf 0.109709499213 against the typed
    0.109709499212 (rel 9.11e-12) with the raw q'. The existing hand-edit test has one rate
    event, whose rounding error (4.2e-13) is below its tolerance; this one is not."""
    doc = _tree_walk_rounding_doc()
    api.open_doc(doc)
    body = api.whatif_ok({"E0": 10, "E2": 10})
    typed = _typed_headline(doc, {"E0": 10, "E2": 10})
    assert typed["headlineMethod"] == "treeWalk" and body["method"] == "treeWalk"
    assert typed["headline"] == W.rel(0.109709499212, 1e-12)
    assert body["whatIf"] == W.rel(typed["headline"], 1e-12)


def test_a_scaled_fixed_event_is_not_rounded_in_the_top_event(api):
    """Only the models' q is rounded to 12 digits by the engine; a fixed event's q is used as
    typed. A group of fixed 0.05000000000024 (13 digits), f = 2 on A: Q_t 0.10000000000048,
    which a build that rounds fixed events too turns into 0.1 (the typed document keeps all
    digits): 0.018019000000124595 against 0.018019000000000004, rel 6.9e-12."""
    q = 0.05000000000024
    doc = W.group_doc(q)
    api.open_doc(doc)
    body = api.whatif_ok({"A": 2})
    typed = W.hand_headline(doc, {"A", "B"}, 2 * q)
    assert typed["headlineMethod"] == "mcub" and body["method"] == "mcub"
    assert body["whatIf"] == W.rel(typed["headline"], 1e-12)
    assert typed["headline"] == W.rel(0.018019000000124595, 1e-12)


def test_an_ordinary_rate_event_in_an_mcub_document_uses_the_engine_q(api):
    """``group_and_rate_doc`` (group g1 on A, B; P a rate event, lambda 1e-5, T 1000; the
    headline is the MCUB because of the group), f = 2 on P: the cut sets that hold P take the
    engine's rounded q of lambda 2e-5, as the same document with lambda typed in. The raw q
    is off by about 2e-12 relative."""
    doc = W.group_and_rate_doc()
    api.open_doc(doc)
    body = api.whatif_ok({"P": 2})
    typed = _typed_headline(doc, {"P": 2})
    assert typed["headlineMethod"] == "mcub" and body["method"] == "mcub"
    assert body["whatIf"] == W.rel(typed["headline"], 1e-12)
    # the rows keep the raw q and the nominal q (rider 1): tidying either changes the 12th digit
    assert W.row_of(body, "P")["q"] == W.rel(-math.expm1(-2e-5 * 1000.0), 1e-14)
    assert W.row_of(body, "P")["nominalQ"] == W.rel(-math.expm1(-1e-5 * 1000.0), 1e-14)


def test_a_standby_group_uses_the_engine_q_in_the_top_event(api):
    """A, B standby (lambda 1.0000000000045e-5, tau 100) in a beta group, f = 2 on A: the raw
    q is 0.0010000000000045001, which the engine rounds to 0.001 (12 digits); the top event of
    the typed document uses the rounded value, the row the raw one. Hand: 0.000100809919; a
    build that does not round a standby q is rel 4.5e-12 away."""
    lam = 1.0000000000045e-5
    doc = W.M.document(W.M.top([W.M.gate("G1", "AND", [
        W.M.leaf(i, 0.0, name="Standby %s" % i, quant=W.standby(lam, 100.0)) for i in ("A", "B")],
        name="Both fail")]), [W.M.group()])
    api.open_doc(doc)
    body = api.whatif_ok({"A": 2})
    typed = _typed_headline(doc, {"A": 2, "B": 2})
    assert typed["headlineMethod"] == "mcub" and body["method"] == "mcub"
    assert body["whatIf"] == W.rel(typed["headline"], 1e-12)
    assert typed["headline"] == W.rel(0.000100809919, 1e-12)
    assert W.row_of(body, "A")["q"] == W.rel(2 * lam * 100.0 / 2.0, 1e-14)


def test_a_rate_event_with_the_mission_time_uses_the_engine_q_in_the_top_event(api):
    """P without a T takes the document's mission time (8760 h). f = 3: lambda 3e-5, raw q
    0.2311043389335145, rounded 0.231104338934: the top event is rel 2.1e-12 away from the
    typed document if it uses the raw q. (f = 2 would be only 4.6e-13 away.)"""
    doc = W.group_and_rate_doc()
    for node in W.walk(doc["tree"]):
        if node["id"] == "P":
            del node["quant"]["T"]
    api.open_doc(doc)
    body = api.whatif_ok({"P": 3})
    typed = _typed_headline(doc, {"P": 3})
    assert typed["headlineMethod"] == "mcub" and body["method"] == "mcub"
    assert body["whatIf"] == W.rel(typed["headline"], 1e-12)
    assert typed["headline"] == W.rel(0.23118185124331153, 1e-12)


def test_an_ordinary_fixed_event_in_an_mcub_document_is_not_rounded(api):
    """``group_and_rate_doc`` with P fixed 0.05000000000024 (13 digits), f = 2: the cut sets
    holding P use 0.10000000000048 as typed. Rounding a fixed event gives 0.1000907289271
    against 0.10009072892757995 (rel 4.8e-12)."""
    q = 0.05000000000024
    doc = W.group_and_rate_doc()
    for node in W.walk(doc["tree"]):
        if node["id"] == "P":
            node["quant"] = {"model": "fixed"}
            node["probability"] = q
    api.open_doc(doc)
    body = api.whatif_ok({"P": 2})
    typed = W.hand_headline(doc, {"P"}, 2 * q)
    assert typed["headlineMethod"] == "mcub" and body["method"] == "mcub"
    assert body["whatIf"] == W.rel(typed["headline"], 1e-12)
    assert typed["headline"] == W.rel(0.10009072892757995, 1e-12)


def test_a_fixed_event_in_a_tree_walk_is_not_rounded(api):
    """OR[E fixed 0.05000000000024, OTH fixed 0.1000000000003], f = 2 on E: the product form
    is 0.190000000000702 as typed; a build that rounds E to 0.1 gets 0.19000000000027, which
    the engine rounds to 0.19 (rel 5.3e-12). OTH puts the two on either side of a 12-digit
    boundary."""
    q = 0.05000000000024
    doc = W.M.document(W.M.top([W.M.leaf("E", q), W.M.leaf("OTH", 0.1000000000003)]), None)
    api.open_doc(doc)
    body = api.whatif_ok({"E": 2})
    typed = W.hand_headline(doc, {"E"}, 2 * q)
    assert typed["headlineMethod"] == "treeWalk" and body["method"] == "treeWalk"
    assert typed["headline"] == W.rel(0.190000000001, 1e-12)
    assert body["whatIf"] == W.rel(typed["headline"], 1e-12)
