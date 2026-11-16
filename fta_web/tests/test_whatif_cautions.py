"""The What-if caution line, server half (feature FR, task X3; CR-20261102-whatif-caution.md,
FR DESIGN sections 1 and 8.1): ``POST /api/whatif`` answers one more field, ``cautions``.

A caution is a machine-coded entry about the WHAT-IF values (never the nominal ones), worked out
from data the endpoint already holds. The four codes mirror what a typed document warns about:

====================  =======================================================  ====================
code                  fires when                                               compare
====================  =======================================================  ====================
``CCF_Q_ONE``         a scaled applied group has a member with q >= 1.0        ``>=`` (ccf.assess)
``CCF_HIGH_Q``        ... else the largest member Q_t is above ccf.HIGH_Q     ``>``  (ccf.assess)
``STANDBY_LARGE_LT``  a scaled standby row has lambda' * tau above 0.2         ``>``  (engine)
``CUTSETS_TRUNCATED`` MCUB headline and order / count / the 2000-set cap       -
====================  =======================================================  ====================

The thresholds are written out below as independent literals (0.01, 0.2), not read from the
product, and cross-checked against ``ccf.HIGH_Q`` where the design says so. Every case whose
outcome rests on a float comparison first asserts the arithmetic it relies on, so a platform
surprise fails loudly there and not in the endpoint.

Y3 (CR-20261104, FR DESIGN section 10) adds a fifth code, ``CCF_NOT_APPLIED`` (first in the order,
entry ``{code, groupIds}``): a factor other than 1 sits on a member of a CCF group that is NOT applied
at baseline, whatever the reason, so the what-if scales that member alone and the CCF event is missing
from the number. Cases N1-N11 and the typed oracle N10 (random documents over every not-applied reason,
the reference being ``ccf.build_plan(...).assessments``) cover it.

The cases go through the real endpoint with the Flask test client on documents opened through
the file route. The helpers of ``acceptance/whatif`` are imported and not edited.
"""
import json
import sys
from pathlib import Path

import pytest

flask = pytest.importorskip("flask")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "acceptance" / "whatif"))
import whatif_support as W  # noqa: E402  (the helpers of the F4 acceptance tests)

M = W.M

#: Independent literals of the thresholds (see the module docstring).
HIGH_Q = 0.01
STANDBY_LT = 0.2

#: What POST /api/whatif answered before X3, plus the new field.
OLD_KEYS = {"ok", "revision", "documentSerial", "baseline", "whatIf", "ratio", "method", "note",
            "truncatedBy", "cache", "baselineMs", "groups", "events"}

#: Y3 (CR-20261104, FR DESIGN 10.1): ``CCF_NOT_APPLIED`` is first; the other four keep their order.
ORDER = ["CCF_NOT_APPLIED", "CCF_Q_ONE", "CCF_HIGH_Q", "STANDBY_LARGE_LT", "CUTSETS_TRUNCATED"]
#: The four codes of X3 (documents that have no group outside the plan fire only these).
FOUR = ORDER[1:]


# ---------------------------------------------------------------- the app


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Credentials in this test's folder; no cache of an earlier test survives."""
    from AI_agent_handler import AICredentialManager
    from fta_web import engine, recovery, whatif

    directory = tmp_path / "fta_editor_home"
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_DIR", directory)
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_FILE", directory / "ai_credentials.json")

    def clear():
        cache = getattr(engine, "_headline_cache", None)
        if cache is not None:
            cache[:] = []
        whatif.clear_cache()

    clear()
    yield
    clear()
    recovery.end_session()


@pytest.fixture
def api(tmp_path):
    from fta_web.state import reset_state

    app = W.make_app(tmp_path)
    with app.test_client() as client:
        yield W.Api(client, tmp_path)
    reset_state()


# ---------------------------------------------------------------- documents


def beta_doc(q, analysis=None):
    """R1 with this member q: root OR [ G1 AND [A, B] ], A and B fixed ``q``, beta group g1 (0.1)."""
    tree = M.top([M.gate("G1", "AND", [M.pump("A", q), M.pump("B", q)], name="Pumps fail")])
    return M.document(tree, [M.group()], analysis=analysis)


def alpha_doc(q):
    """AND [A, B, C], fixed ``q``, one alpha group (0.9, 0.06, 0.04), staggered testing."""
    tree = M.top([M.gate("G1", "AND", [M.pump(m, q) for m in "ABC"], name="Pumps fail")])
    group = M.group(model="alpha", beta=None, alpha=[0.9, 0.06, 0.04], testing="staggered",
                    members=("A", "B", "C"))
    return M.document(tree, [group])


def standby_event(node_id, lam, tau):
    return M.leaf(node_id, 0.0, name="Standby " + node_id, quant=W.standby(lam, tau))


def standby_doc(lam, tau, **extra):
    """root OR [ S standby (lambda, tau), OTH fixed 1e-3 ]."""
    return M.document(M.top([standby_event("S", lam, tau), M.leaf("OTH", 1e-3, name="Other event")]),
                      None, **extra)


def two_standby_doc(first, second):
    """root OR [ S1 standby (lambda, tau), S2 standby ]: no group."""
    return M.document(M.top([standby_event("S1", *first), standby_event("S2", *second)]), None)


def standby_group_doc(lam, tau):
    """AND [S1, S2], two identical standby events in one beta group g1."""
    tree = M.top([M.gate("G1", "AND", [standby_event("S1", lam, tau), standby_event("S2", lam, tau)],
                         name="Standby pair fails")])
    return M.document(tree, [M.group(members=("S1", "S2"))])


def two_beta_groups_doc(q1, q2):
    """OR [ G1 AND [A, B], G2 AND [D, E] ]: beta groups g1 (A, B at q1) and g2 (D, E at q2)."""
    tree = M.top([M.gate("G1", "AND", [M.pump("A", q1), M.pump("B", q1)], name="Pumps fail"),
                  M.gate("G2", "AND", [M.pump("D", q2), M.pump("E", q2)], name="Valves fail"),
                  M.leaf("Z", 1e-3, name="Sensor Z")])
    return M.document(tree, [M.group(), M.group("g2", "Valves", members=("D", "E"))])


def three_gate_tree():
    """AND [ G1 OR [A, B], G2 OR [X (OR link to A), C], G3 OR [D, E] ]: A is reached twice (an
    MCUB headline). Cut sets: {A, D}, {A, E} (order 2) and four of order 3 through B."""
    return M.gate("root", "AND", [
        M.gate("G1", "OR", [M.leaf("A", 0.01, name="Event A"), M.leaf("B", 0.1, name="Event B")],
               name="Branch 1"),
        M.gate("G2", "OR", [
            M.leaf("X", 0.0, name="Event X", links=[{"target_id": "A", "relation": "OR"}]),
            M.leaf("C", 0.1, name="Event C")], name="Branch 2"),
        M.gate("G3", "OR", [M.leaf("D", 0.1, name="Event D"), M.leaf("E", 0.1, name="Event E")],
               name="Branch 3"),
    ], name="Top event", type_="Root")


def cutsets_doc(**limits):
    """The repeated-event tree of the acceptance helpers with these ``analysis.cutsets`` limits."""
    return M.document(W.repeated_tree(), None, analysis={"cutsets": dict(limits)})


def all_four_doc():
    """One document that can fire all four codes: g1 (A, B at 0.5), g2 (D, E at 0.05), a standby
    S (lambda 0.05, tau 2, lt 0.1), and a maxOrder 1 limit on the cut sets."""
    tree = M.top([M.gate("G1", "AND", [M.pump("A", 0.5), M.pump("B", 0.5)], name="Pumps fail"),
                  M.gate("G2", "AND", [M.pump("D", 0.05), M.pump("E", 0.05)], name="Valves fail"),
                  standby_event("S", 0.05, 2.0)])
    return M.document(tree, [M.group(), M.group("g2", "Valves", members=("D", "E"))],
                      analysis={"cutsets": {"maxOrder": 1}})


ALL_FOUR_FACTORS = {"A": 2, "D": 1.2, "S": 2.0000001}


def all_five_doc():
    """``all_four_doc`` plus g3 on F and H, which differ (2e-3 against 1e-3): g3 is not applied."""
    tree = M.top([M.gate("G1", "AND", [M.pump("A", 0.5), M.pump("B", 0.5)], name="Pumps fail"),
                  M.gate("G2", "AND", [M.pump("D", 0.05), M.pump("E", 0.05)], name="Valves fail"),
                  M.gate("G3", "AND", [M.pump("F", 1e-3), M.pump("H", 2e-3)], name="Fans fail"),
                  standby_event("S", 0.05, 2.0)])
    groups = [M.group(), M.group("g2", "Valves", members=("D", "E")),
              M.group("g3", "Fans", members=("F", "H"))]
    return M.document(tree, groups, analysis={"cutsets": {"maxOrder": 1}})


ALL_FIVE_FACTORS = {"A": 2, "D": 1.2, "F": 2, "S": 2.0000001}


# ---------------------------------------------------------------- readers


def cautions_of(body):
    """The ``cautions`` list of a response, which must exist and be a list."""
    assert "cautions" in body, "the response has no cautions key: %s" % sorted(body)
    assert isinstance(body["cautions"], list), body["cautions"]
    return body["cautions"]


def codes_of(body):
    return [c["code"] for c in cautions_of(body)]


def entry_of(body, code):
    found = [c for c in cautions_of(body) if c["code"] == code]
    assert len(found) == 1, (code, cautions_of(body))
    return found[0]


def ask(api, doc, factors):
    """Open ``doc`` and answer the what-if for ``factors``."""
    api.open_doc(doc)
    return api.whatif_ok(factors)


# ---------------------------------------------------------------- S: shape, no factor, no caution


def test_s1_the_field_is_always_present_and_a_list(api):
    """R1: ``{}`` gives ``[]``; ``{"A": 10}`` gives a list too (here: empty, Q_t 0.01 is not above)."""
    api.open_doc(W.r1_doc())
    first = api.whatif_ok({})
    assert cautions_of(first) == []
    second = api.whatif_ok({"A": 10})
    assert isinstance(cautions_of(second), list)
    # and the thresholds this file uses are the product's
    from fta_web import ccf

    assert ccf.HIGH_Q == HIGH_Q


@pytest.mark.parametrize("doc, factors", [
    pytest.param(W.r1_doc(), {}, id="r1-no-factor"),
    pytest.param(W.r1_doc(), {"A": 10}, id="r1-factor"),
    pytest.param(W.models_doc(), {"RATE": 10}, id="tree-walk-factor"),
    pytest.param(W.models_doc(), {}, id="tree-walk-no-factor"),
    pytest.param(W.unapplied_group_doc(), {"A": 100}, id="group-not-applied"),
    pytest.param(W.repeated_doc(), {"A": 2}, id="repeated-events"),
    pytest.param(cutsets_doc(maxOrder=1), {"A": 10}, id="cut-set-limit"),
    pytest.param(standby_doc(0.05, 2.0), {"S": 2}, id="standby"),
    pytest.param(two_beta_groups_doc(0.5, 0.05), {"A": 2, "D": 1.2}, id="two-groups"),
])
def test_s1_cautions_is_a_list_for_every_kind_of_document(api, doc, factors):
    body = ask(api, doc, factors)
    assert isinstance(cautions_of(body), list)
    json.dumps(body["cautions"])           # plain JSON values


def test_s1_the_old_keys_and_their_values_are_unchanged(api):
    """R1, factor 10 on A: exactly the answer of F4 (the hand values of acceptance/whatif) plus the
    one new key."""
    body = ask(api, W.r1_doc(), {"A": 10})
    assert set(body) == OLD_KEYS | {"cautions"}
    assert body["method"] == "mcub" and body["note"] is None and body["truncatedBy"] == []
    assert body["baseline"] == W.rel(W.R1_BASELINE, 1e-9)
    assert body["whatIf"] == W.rel(W.R1_F10, 1e-9)
    assert body["ratio"] == W.rel(W.R1_F10_RATIO, 1e-9)
    assert [g["id"] for g in body["groups"]] == ["g1"]
    assert [r["id"] for r in body["events"]] == ["A", "B"]
    assert body["cache"] == "miss"
    assert cautions_of(body) == []


def test_s2_a_document_that_already_warns_at_nominal_values_is_silent_without_a_factor(api):
    """Q_t 0.05 at nominal (above 0.01), lambda*tau 0.5 at nominal (above 0.2), a maxOrder limit:
    with no factor, or only factor 1, nothing is a caution (the tab must not warn by being opened)."""
    api.open_doc(beta_doc(0.05))
    assert cautions_of(api.whatif_ok({})) == []
    assert cautions_of(api.whatif_ok({"A": 1})) == []
    assert cautions_of(api.whatif_ok({"A": 1, "B": 1})) == []

    api.open_doc(standby_doc(0.25, 2.0))             # lambda * tau = 0.5
    assert cautions_of(api.whatif_ok({})) == []
    assert cautions_of(api.whatif_ok({"S": 1})) == []

    api.open_doc(cutsets_doc(maxOrder=1))
    body = api.whatif_ok({})
    assert "order" in body["truncatedBy"] and body["method"] == "mcub"        # the premise
    assert cautions_of(body) == []
    assert cautions_of(api.whatif_ok({"A": 1})) == []


def test_s2_a_scaled_event_warns_even_when_the_nominal_value_already_did(api):
    """The what-if value is the one that is shown: Q_t 0.05 at nominal, factor 1.1 -> 0.055."""
    body = ask(api, beta_doc(0.05), {"A": 1.1})
    assert codes_of(body) == ["CCF_HIGH_Q"]


# ---------------------------------------------------------------- C: CCF_Q_ONE


def test_c1_q_one_fires_at_exactly_one(api):
    """q 0.5, factor 2: Q_t = 1.0 exactly (not clamped); the check is non-strict (>=)."""
    assert 0.5 * 2 == 1.0
    body = ask(api, beta_doc(0.5), {"A": 2})
    assert codes_of(body) == ["CCF_Q_ONE"]
    assert entry_of(body, "CCF_Q_ONE")["groupIds"] == ["g1"]
    assert [r["q"] for r in body["events"]] == [1.0, 1.0]
    assert [r["clamped"] for r in body["events"]] == [False, False]      # raw q is exactly 1


def test_c2_q_one_fires_for_a_clamped_member_and_hides_high_q(api):
    body = ask(api, beta_doc(0.5), {"A": 10})
    assert codes_of(body) == ["CCF_Q_ONE"]                  # CCF_HIGH_Q never joins it for the same group
    assert entry_of(body, "CCF_Q_ONE")["groupIds"] == ["g1"]
    assert all(r["clamped"] is True and r["q"] == 1.0 for r in body["events"])


def test_c3_just_below_one_is_high_q_only(api):
    """0.5 * 1.999999 = 0.9999995, below 1: a warning (above 0.01), not the error."""
    assert 0.5 * 1.999999 < 1.0
    body = ask(api, beta_doc(0.5), {"A": 1.999999})
    assert codes_of(body) == ["CCF_HIGH_Q"]
    assert entry_of(body, "CCF_HIGH_Q")["groupIds"] == ["g1"]


# ---------------------------------------------------------------- H: CCF_HIGH_Q


def test_h1_high_q_is_strict_at_the_boundary(api):
    """Q_t exactly 0.01 is not above ccf.HIGH_Q."""
    from fta_web import ccf

    assert 0.005 * 2 == 0.01 == HIGH_Q == ccf.HIGH_Q
    assert 1e-3 * 10 == 0.01
    assert cautions_of(ask(api, beta_doc(0.005), {"A": 2})) == []
    assert cautions_of(ask(api, beta_doc(1e-3), {"A": 10})) == []


def test_h2_high_q_fires_just_above(api):
    from fta_web import ccf

    assert 0.005 * 2.0000001 > 0.01
    assert 1e-3 * 10.5 > 0.01
    for q, factor in ((0.005, 2.0000001), (1e-3, 10.5)):
        body = ask(api, beta_doc(q), {"A": factor})
        assert codes_of(body) == ["CCF_HIGH_Q"], (q, factor)
        found = entry_of(body, "CCF_HIGH_Q")
        assert found["groupIds"] == ["g1"]
        assert found["limit"] == ccf.HIGH_Q == HIGH_Q


def test_h3_alpha_group_has_the_same_boundary(api):
    assert 0.005 * 2 == 0.01 and 0.005 * 2.0000001 > 0.01
    above = ask(api, alpha_doc(0.005), {"A": 2.0000001})
    assert codes_of(above) == ["CCF_HIGH_Q"]
    assert entry_of(above, "CCF_HIGH_Q")["groupIds"] == ["g1"]
    assert cautions_of(ask(api, alpha_doc(0.005), {"A": 2})) == []


def test_h4_a_factor_below_one_still_warns_while_the_what_if_value_is_above(api):
    assert 0.05 * 0.5 > 0.01 and 0.05 * 0.1 < 0.01
    assert codes_of(ask(api, beta_doc(0.05), {"A": 0.5})) == ["CCF_HIGH_Q"]
    assert cautions_of(ask(api, beta_doc(0.05), {"A": 0.1})) == []


def test_h5_two_groups_each_group_in_one_code_and_the_error_first(api):
    """g1 reaches Q_t 1, g2 is at 0.06: ``CCF_Q_ONE`` (g1) then ``CCF_HIGH_Q`` (g2)."""
    assert 0.5 * 2 == 1.0 and 0.05 * 1.2 > 0.01
    body = ask(api, two_beta_groups_doc(0.5, 0.05), {"A": 2, "D": 1.2})
    assert codes_of(body) == ["CCF_Q_ONE", "CCF_HIGH_Q"]
    assert entry_of(body, "CCF_Q_ONE")["groupIds"] == ["g1"]
    assert entry_of(body, "CCF_HIGH_Q")["groupIds"] == ["g2"]


def test_h5_group_ids_follow_the_plan_order_not_the_request_order(api):
    """Both groups at 0.06; the request names a member of g2 first (written as text, as ``json=``
    sorts the keys): the ids are still ``["g1", "g2"]``."""
    api.open_doc(two_beta_groups_doc(0.05, 0.05))
    status, body = api.raw_with('{"E": 1.2, "A": 1.2}')
    assert status == 200, body
    assert codes_of(body) == ["CCF_HIGH_Q"]
    assert entry_of(body, "CCF_HIGH_Q")["groupIds"] == ["g1", "g2"]


def test_h6_a_group_that_was_not_asked_never_warns(api):
    """g2 sits at Q_t 0.05 (above 0.01) but no member has a factor: only the other group, or a
    non-member, is scaled."""
    api.open_doc(two_beta_groups_doc(1e-3, 0.05))
    assert cautions_of(api.whatif_ok({"Z": 2})) == []
    assert cautions_of(api.whatif_ok({"A": 2})) == []            # g1 at 0.002, g2 not asked
    assert cautions_of(api.whatif_ok({"D": 1})) == []            # asked with factor 1: not scaled
    assert codes_of(api.whatif_ok({"A": 2, "D": 1.2})) == ["CCF_HIGH_Q"]
    assert entry_of(api.whatif_ok({"A": 2, "D": 1.2}), "CCF_HIGH_Q")["groupIds"] == ["g2"]


NOT_APPLIED_G1 = {"code": "CCF_NOT_APPLIED", "groupIds": ["g1"]}


def test_h7_a_group_that_is_not_applied_at_baseline_is_outside_the_what_if_and_says_so(api):
    """Rewritten for Y3 (was: ``[]``). A (1e-3) and B (2e-3) differ, so FN-33 does not apply the
    group: whatever the factor does to them, there is no CCF group in the what-if (``groups == []``,
    members are scaled one by one), and the one caution is ``CCF_NOT_APPLIED`` for g1. Q_ONE and
    HIGH_Q never join it, although the factors push the members past 0.01 (and past 1). The second
    document does the same with members (0.5 and 0.6) that a factor pushes to q = 1."""
    api.open_doc(W.unapplied_group_doc())
    for factors in ({"A": 100}, {"A": 100, "B": 100}, {"B": 100}, {"B": 50}):
        body = api.whatif_ok(factors)
        assert body["groups"] == [], factors
        assert cautions_of(body) == [NOT_APPLIED_G1], factors
        assert all(r["viaGroup"] is False and r["groupId"] is None for r in body["events"]), factors

    tree = M.top([M.gate("G1", "AND", [M.pump("A", 0.5), M.pump("B", 0.6)], name="Pumps fail")])
    api.open_doc(M.document(tree, [M.group()]))
    assert 0.5 * 2 == 1.0
    for factors in ({"A": 2}, {"A": 10}, {"B": 100}):
        body = api.whatif_ok(factors)
        assert body["groups"] == [], factors
        assert cautions_of(body) == [NOT_APPLIED_G1], factors
        assert "CCF_Q_ONE" not in codes_of(body) and "CCF_HIGH_Q" not in codes_of(body), factors


def test_h8_via_group_rows_evaluate_the_group_once(api):
    """The factor on B only (or on A and B alike): the group is evaluated once, listed once."""
    assert 1e-3 * 20 > 0.01
    api.open_doc(W.r1_doc())
    for factors in ({"B": 20}, {"A": 20}, {"A": 20, "B": 20}):
        body = api.whatif_ok(factors)
        assert codes_of(body) == ["CCF_HIGH_Q"], factors
        assert entry_of(body, "CCF_HIGH_Q")["groupIds"] == ["g1"], factors
    body = api.whatif_ok({"B": 20})
    assert [(r["id"], r["viaGroup"]) for r in body["events"]] == [("B", False), ("A", True)]


# ---------------------------------------------------------------- T: STANDBY_LARGE_LT


def test_t1_standby_fires_when_lambda_tau_is_above_the_limit(api):
    """lambda 0.05, tau 2: lambda' = 2.0000001 * 0.05, lambda' * tau just above 0.2."""
    assert (2.0000001 * 0.05) * 2 > 0.2
    body = ask(api, standby_doc(0.05, 2.0), {"S": 2.0000001})
    assert codes_of(body) == ["STANDBY_LARGE_LT"]
    found = entry_of(body, "STANDBY_LARGE_LT")
    assert found["eventIds"] == ["S"]
    assert found["limit"] == STANDBY_LT


def test_t2_standby_is_strict_at_the_boundary(api):
    """lambda' * tau is exactly 0.2 (the same float as the literal), which is not above."""
    assert (2 * 0.05) * 2 == 0.2
    assert cautions_of(ask(api, standby_doc(0.05, 2.0), {"S": 2})) == []


def test_t3_the_test_is_on_lambda_tau_not_on_lambda_tau_over_two(api):
    """lambda 0.05, tau 3, factor 2: lambda' * tau = 0.3 (above 0.2) but q = 0.15 (below 0.2)."""
    assert (2 * 0.05) * 3 > 0.2 and (2 * 0.05) * 3 / 2 < 0.2
    body = ask(api, standby_doc(0.05, 3.0), {"S": 2})
    assert codes_of(body) == ["STANDBY_LARGE_LT"]
    assert body["events"][0]["q"] < STANDBY_LT


def test_t4_a_clamped_standby_event_fires(api):
    """lambda 1e-3, tau 1000, factor 10: lambda' * tau = 10 and lambda' * tau / 2 = 5 > 1 (clamped)."""
    body = ask(api, W.standby_clamp_doc(), {"SBY": 10})
    row = W.row_of(body, "SBY")
    assert row["clamped"] is True and row["q"] == 1.0
    assert codes_of(body) == ["STANDBY_LARGE_LT"]
    assert entry_of(body, "STANDBY_LARGE_LT")["eventIds"] == ["SBY"]


def test_t5_a_factor_below_one_still_fires_while_the_what_if_value_is_above(api):
    """lambda 0.25, tau 2 (nominal 0.5), factor 0.5 -> 0.25; and lambda 0.2, factor 0.5 -> exactly 0.2."""
    assert (0.5 * 0.25) * 2 > 0.2
    assert codes_of(ask(api, standby_doc(0.25, 2.0), {"S": 0.5})) == ["STANDBY_LARGE_LT"]
    assert (0.5 * 0.2) * 2 == 0.2
    assert cautions_of(ask(api, standby_doc(0.2, 2.0), {"S": 0.5})) == []


def test_t6_only_scaled_events_count(api):
    """S1 sits at lambda*tau 0.5 at nominal; S2 (0.1) is scaled past 0.2. S1 is not asked, or asked
    with factor 1: it is not in the caution."""
    assert (2.0000001 * 0.05) * 2 > 0.2
    api.open_doc(two_standby_doc((0.25, 2.0), (0.05, 2.0)))
    for factors in ({"S2": 2.0000001}, {"S1": 1, "S2": 2.0000001}):
        body = api.whatif_ok(factors)
        assert codes_of(body) == ["STANDBY_LARGE_LT"], factors
        assert entry_of(body, "STANDBY_LARGE_LT")["eventIds"] == ["S2"], factors
    both = api.whatif_ok({"S1": 1.5, "S2": 2.0000001})
    assert entry_of(both, "STANDBY_LARGE_LT")["eventIds"] == ["S1", "S2"]


def test_t7_other_models_never_give_the_standby_caution(api):
    """Rate, repairable and fixed events with the largest factor (100): no standby code."""
    body = ask(api, W.models_doc(), {"RATE": 100, "REPA": 100, "FIX": 100})
    assert body["method"] == "treeWalk"
    assert "STANDBY_LARGE_LT" not in codes_of(body)
    assert cautions_of(body) == []
    # the standby event of the same document, not asked, is not in it either
    assert W.row_of(body, "RATE")["model"] == "rate"


def test_t8_standby_members_of_a_group_all_count(api):
    """S1, S2 identical standby events in one beta group; the factor on S2 scales both (S1 via the
    group). Both are listed, in row order: the requested event first."""
    assert (2.0000001 * 0.05) * 2 > 0.2
    body = ask(api, standby_group_doc(0.05, 2.0), {"S2": 2.0000001})
    assert [(r["id"], r["viaGroup"]) for r in body["events"]] == [("S2", False), ("S1", True)]
    assert codes_of(body) == ["CCF_HIGH_Q", "STANDBY_LARGE_LT"]          # Q_t is about 0.1 > 0.01
    assert entry_of(body, "STANDBY_LARGE_LT")["eventIds"] == ["S2", "S1"]
    assert entry_of(body, "CCF_HIGH_Q")["groupIds"] == ["g1"]


# ---------------------------------------------------------------- K: CUTSETS_TRUNCATED


def test_k1_order_limit(api):
    body = ask(api, cutsets_doc(maxOrder=1), {"A": 10})
    assert body["method"] == "mcub" and body["truncatedBy"] == ["order"]            # the premise
    assert codes_of(body) == ["CUTSETS_TRUNCATED"]
    assert entry_of(body, "CUTSETS_TRUNCATED")["by"] == ["order"]


def test_k2_count_limit(api):
    body = ask(api, cutsets_doc(maxCount=1), {"A": 10})
    assert body["method"] == "mcub" and body["truncatedBy"] == ["count"]
    assert codes_of(body) == ["CUTSETS_TRUNCATED"]
    assert entry_of(body, "CUTSETS_TRUNCATED")["by"] == ["count"]


def test_k3_order_and_count_are_listed_in_the_fixed_order(api):
    """The engine lists ``count`` before ``order`` in ``truncatedBy``; the caution's ``by`` is
    ``["order", "count"]`` whatever that order is."""
    body = ask(api, cutsets_doc(maxOrder=1, maxCount=1), {"A": 10})
    assert sorted(body["truncatedBy"]) == ["count", "order"]
    assert entry_of(body, "CUTSETS_TRUNCATED")["by"] == ["order", "count"]


def test_k4_the_summary_cap_is_reported_as_count(api, monkeypatch):
    """The headline's own cap (SUMMARY_LIMITS maxCount, patched below the document's maxCount) cuts
    the cut sets short: ``capped`` is true and the response's ``truncatedBy`` does not say so; the
    caution reports it as ``count``."""
    from fta_web import engine

    monkeypatch.setitem(engine.SUMMARY_LIMITS, "maxCount", 1)
    api.open_doc(W.repeated_doc())
    assert api.summary()["capped"] is True                                          # the premise
    body = api.whatif_ok({"A": 10})
    assert body["method"] == "mcub" and body["truncatedBy"] == []
    assert codes_of(body) == ["CUTSETS_TRUNCATED"]
    assert entry_of(body, "CUTSETS_TRUNCATED")["by"] == ["count"]


def test_k5_a_cutoff_alone_gives_the_note_and_no_caution(api):
    body = ask(api, W.r1_cutoff_doc(), {"A": 5})
    assert body["truncatedBy"] == ["cutoff"] and body["method"] == "mcub"
    assert body["note"] == "cutsets_from_nominal"
    assert cautions_of(body) == []


def test_k6_cutoff_with_order_gives_the_note_and_the_caution(api):
    """A cutoff and an order limit that both drop sets: the note is the cutoff's, the caution
    names only order and count (the texts differ, so nothing is said twice)."""
    doc = M.document(three_gate_tree(), None, analysis={"cutsets": {"maxOrder": 2, "cutoff": 1e-2}})
    body = ask(api, doc, {"B": 2})
    assert sorted(body["truncatedBy"]) == ["cutoff", "order"]                       # the premise
    assert body["note"] == "cutsets_from_nominal"
    assert codes_of(body) == ["CUTSETS_TRUNCATED"]
    assert entry_of(body, "CUTSETS_TRUNCATED")["by"] == ["order"]


def test_k7_a_tree_walk_headline_gives_no_cut_set_caution(api):
    """No repeated event: the headline is the tree walk, which does not use the cut sets, even
    though ``truncatedBy`` says order."""
    body = ask(api, M.document(W.and_of_ors_doc()["tree"], None, analysis={"cutsets": {"maxOrder": 1}}),
               {"A": 5})
    assert body["method"] == "treeWalk" and body["truncatedBy"] == ["order"]
    assert cautions_of(body) == []


def test_k8_an_incomplete_headline_has_no_cut_set_caution_but_keeps_the_ccf_codes(api, monkeypatch):
    from fta_web import engine

    monkeypatch.setitem(engine.SUMMARY_LIMITS, "maxCount", 1)
    monkeypatch.setitem(engine.SUMMARY_LIMITS, "timeBudgetS", 2.0)
    api.open_doc(W.r1_doc())
    assert api.summary()["headlineMethod"] == "incomplete"
    quiet = api.whatif_ok({"A": 2})                      # Q_t 0.002: nothing fires
    assert quiet["method"] == "incomplete" and quiet["note"] == "incomplete"
    assert cautions_of(quiet) == []
    loud = api.whatif_ok({"A": 20})                      # Q_t 0.02: the group is above 0.01
    assert loud["method"] == "incomplete" and loud["whatIf"] is None
    assert codes_of(loud) == ["CCF_HIGH_Q"]
    assert "CUTSETS_TRUNCATED" not in codes_of(loud)

    api.open_doc(beta_doc(0.5))
    over = api.whatif_ok({"A": 2})
    assert over["method"] == "incomplete"
    assert codes_of(over) == ["CCF_Q_ONE"]


def test_k9_a_timed_out_cut_set_run_gives_no_cut_set_caution(api, monkeypatch):
    """The cut sets ran out of time: ``truncatedBy`` has ``time`` and the headline is no cut-set
    number, so "cut sets limited" would be false. With a maxOrder limit in the document too."""
    from fta_web import cutsets

    def fail(*args, **kwargs):
        raise cutsets.CutsetError("time", "The cut-set time budget ran out.")

    monkeypatch.setattr(cutsets, "compute", fail)
    body = ask(api, cutsets_doc(maxOrder=1), {"A": 10})
    assert "time" in body["truncatedBy"] and body["method"] == "treeWalk"
    assert cautions_of(body) == []
    api.open_doc(W.r1_doc())
    group = api.whatif_ok({"A": 20})                    # the CCF caution of the same document stays
    assert "time" in group["truncatedBy"] and group["method"] == "incomplete"
    assert codes_of(group) == ["CCF_HIGH_Q"]


@pytest.mark.parametrize("case", ["order", "count", "both", "cap"])
@pytest.mark.parametrize("factors", [{}, {"A": 1}, {"A": 1, "X": 1}])
def test_k10_no_factor_no_cut_set_caution(api, monkeypatch, case, factors):
    """The truncation is the baseline's own; it is reported only while a factor is active."""
    if case == "cap":
        from fta_web import engine

        monkeypatch.setitem(engine.SUMMARY_LIMITS, "maxCount", 1)
        doc = W.repeated_doc()
    else:
        limits = {"order": {"maxOrder": 1}, "count": {"maxCount": 1},
                  "both": {"maxOrder": 1, "maxCount": 1}}[case]
        doc = cutsets_doc(**limits)
    api.open_doc(doc)
    body = api.whatif_ok(factors)
    assert body["method"] == "mcub"
    assert cautions_of(body) == []
    # the same document with a factor does give the caution (the case is a real one)
    assert codes_of(api.whatif_ok({"A": 10})) == ["CUTSETS_TRUNCATED"]


# ---------------------------------------------------------------- O: order, cache, isolation, shape


def test_o1_the_four_x3_codes_in_the_fixed_order(api):
    body = ask(api, all_four_doc(), ALL_FOUR_FACTORS)
    assert codes_of(body) == FOUR                       # no group outside the plan: no CCF_NOT_APPLIED
    assert entry_of(body, "CCF_Q_ONE")["groupIds"] == ["g1"]
    assert entry_of(body, "CCF_HIGH_Q")["groupIds"] == ["g2"]
    assert entry_of(body, "STANDBY_LARGE_LT")["eventIds"] == ["S"]
    assert entry_of(body, "CUTSETS_TRUNCATED")["by"] == ["order"]
    # a request in another key order gives the same list
    api.open_doc(all_four_doc())
    status, other = api.raw_with('{"S": 2.0000001, "D": 1.2, "A": 2}')
    assert status == 200, other
    assert other["cautions"] == body["cautions"]


def test_o1b_all_five_codes_in_the_fixed_order_not_applied_first(api):
    """Y3: g1 at Q_t 1, g2 at 0.06, g3 (F, H) not applied, a scaled standby event, a maxOrder limit."""
    body = ask(api, all_five_doc(), ALL_FIVE_FACTORS)
    assert codes_of(body) == ORDER
    assert entry_of(body, "CCF_NOT_APPLIED")["groupIds"] == ["g3"]
    assert entry_of(body, "CCF_Q_ONE")["groupIds"] == ["g1"]
    assert entry_of(body, "CCF_HIGH_Q")["groupIds"] == ["g2"]
    assert entry_of(body, "STANDBY_LARGE_LT")["eventIds"] == ["S"]
    assert entry_of(body, "CUTSETS_TRUNCATED")["by"] == ["order"]
    assert [g["id"] for g in body["groups"]] == ["g1", "g2"]            # g3 is outside the plan
    api.open_doc(all_five_doc())
    status, other = api.raw_with('{"S": 2.0000001, "F": 2, "D": 1.2, "A": 2}')
    assert status == 200, other
    assert other["cautions"] == body["cautions"]


def test_o2_cautions_follow_the_request_not_the_cache(api):
    """One baseline: the first request fires (miss), the second (another factor) does not (hit),
    the third fires again, and a repeat of the first answers the same list (miss and hit equal)."""
    assert 0.005 * 2 == 0.01 and 0.005 * 2.0000001 > 0.01
    api.open_doc(beta_doc(0.005))
    first = api.whatif_ok({"A": 2.0000001})
    second = api.whatif_ok({"A": 2})
    third = api.whatif_ok({"A": 2.0000001})
    fourth = api.whatif_ok({"A": 2.0000001})
    assert [first["cache"], second["cache"], third["cache"], fourth["cache"]] == ["miss", "hit", "hit", "hit"]
    assert codes_of(first) == ["CCF_HIGH_Q"]
    assert cautions_of(second) == []
    assert third["cautions"] == first["cautions"] == fourth["cautions"]


def test_o2_miss_and_hit_are_equal_for_every_code(api):
    api.open_doc(all_four_doc())
    first = api.whatif_ok(ALL_FOUR_FACTORS)
    second = api.whatif_ok(ALL_FOUR_FACTORS)
    assert (first["cache"], second["cache"]) == ("miss", "hit")
    assert codes_of(first) == FOUR
    assert second["cautions"] == first["cautions"]
    json.dumps(second["cautions"])
    api.open_doc(all_five_doc())
    third = api.whatif_ok(ALL_FIVE_FACTORS)
    fourth = api.whatif_ok(ALL_FIVE_FACTORS)
    assert (third["cache"], fourth["cache"]) == ("miss", "hit")
    assert codes_of(third) == ORDER
    assert fourth["cautions"] == third["cautions"]


def test_o3_the_endpoint_still_changes_nothing(api):
    api.open_doc(all_four_doc())
    before = W.fingerprint()
    body = api.whatif_ok(ALL_FOUR_FACTORS)
    assert codes_of(body) == FOUR
    assert W.fingerprint() == before
    api.open_doc(all_five_doc())
    before = W.fingerprint()
    assert codes_of(api.whatif_ok(ALL_FIVE_FACTORS)) == ORDER
    assert W.fingerprint() == before


def test_o4_every_entry_has_exactly_the_keys_of_its_code(api):
    doc = all_five_doc()
    body = ask(api, doc, ALL_FIVE_FACTORS)
    found = cautions_of(body)
    assert [c["code"] for c in found] == ORDER
    assert len({c["code"] for c in found}) == len(found)                   # at most one per code
    keys = {"CCF_NOT_APPLIED": {"code", "groupIds"},
            "CCF_Q_ONE": {"code", "groupIds"}, "CCF_HIGH_Q": {"code", "groupIds", "limit"},
            "STANDBY_LARGE_LT": {"code", "eventIds", "limit"}, "CUTSETS_TRUNCATED": {"code", "by"}}
    for item in found:
        assert set(item) == keys[item["code"]], item
    group_ids = {g["id"] for g in doc["analysis"]["ccfGroups"]}
    event_ids = {node["id"] for node in W.walk(doc["tree"])}
    for item in found:
        assert all(i in group_ids for i in item.get("groupIds", [])), item
        assert all(i in event_ids for i in item.get("eventIds", [])), item
        assert all(isinstance(i, str) for i in item.get("groupIds", []) + item.get("eventIds", []))
        if item["code"] != "CCF_NOT_APPLIED":       # only this code may list no id (a group without an id)
            assert item.get("groupIds", item.get("eventIds", item.get("by"))), item
    assert "limit" not in entry_of(body, "CCF_NOT_APPLIED")
    assert all(x in ("order", "count") for x in entry_of(body, "CUTSETS_TRUNCATED")["by"])
    limits = {c["code"]: c["limit"] for c in found if "limit" in c}
    assert limits == {"CCF_HIGH_Q": HIGH_Q, "STANDBY_LARGE_LT": STANDBY_LT}
    assert all(type(v) is float for v in limits.values())                  # JSON numbers
    # nothing of the user's data: no Q_t, no lambda*tau, only ids, the threshold and the sources
    text = json.dumps(found)
    assert json.loads(text) == found


# ---------------------------------------------------------------- P: parity with a typed document


@pytest.mark.parametrize("q, factor", [
    (0.5, 2), (0.5, 1.999999), (0.5, 10), (0.005, 2), (0.005, 2.0000001), (1e-3, 10), (1e-3, 10.5),
    (0.05, 0.5), (0.05, 0.1), (0.05, 0.2), (0.3, 3), (0.3, 3.5), (1e-4, 99.99), (1e-4, 100),
])
def test_p1_the_ccf_caution_is_what_the_typed_document_warns(api, q, factor):
    """The what-if of ``factor`` on a member and the document with ``factor * q`` typed into both
    members (the Grid / Details route): the typed group status is CCF_Q_ONE (not applied), or
    applied with CCF_HIGH_Q, or applied and silent; the what-if cautions say the same."""
    body = ask(api, beta_doc(q), {"A": factor})
    got = [c["code"] for c in cautions_of(body) if c["code"].startswith("CCF_")]

    typed = min(1.0, factor * q)            # a q above 1 cannot be typed; the what-if clamps it
    api.open_doc(beta_doc(typed))
    (group,) = api.get("/api/ccf/groups")[1]["groups"]
    warnings = [w["code"] for w in group["status"].get("warnings") or []]
    if group["status"]["code"] == "CCF_Q_ONE":
        expected = ["CCF_Q_ONE"]
    elif "CCF_HIGH_Q" in warnings:
        expected = ["CCF_HIGH_Q"]
    else:
        expected = []
    assert got == expected, (q, factor, typed, group["status"])


@pytest.mark.parametrize("lam, tau, factor", [
    (0.05, 2.0, 2), (0.05, 2.0, 2.0000001), (0.05, 3.0, 2), (0.25, 2.0, 0.5), (0.2, 2.0, 0.5),
    (1e-3, 1000.0, 10), (1e-4, 100.0, 10), (1e-4, 100.0, 100), (0.1, 1.0, 2), (0.1, 1.0, 2.0000001),
])
def test_p2_the_standby_caution_is_what_derive_quant_warns(api, lam, tau, factor):
    from fta_web import engine

    body = ask(api, standby_doc(lam, tau), {"S": factor})
    fired = "STANDBY_LARGE_LT" in codes_of(body)
    node = {"id": "S", "quant": {"model": "standby", "lambda": factor * lam, "tau": tau}}
    typed = [w["code"] for w in engine.derive_quant(node, None)["warnings"]]
    assert fired == ("STANDBY_LARGE_LT" in typed), (lam, tau, factor)


# ---------------------------------------------------------------- R: the RAW q decides Q_ONE and HIGH_Q
#
# ``ccf.assess`` reads the q of ``derive_quant`` (the raw model q, not rounded); the engine's cut sets use the
# same q rounded to 12 significant digits (``engine._tidy``). The caution mirrors the typed document, so it
# compares the raw q (``row["q"]``, ``scaled[m][3]``). A rate member with lambda*T of about 30 has raw q
# 1 - 1e-13: below 1 for the typed document (applied, CCF_HIGH_Q), 1.0 for the engine. Engineering review of X3.


def rate_group_doc(lam, hours=1000.0):
    """AND [A, B], two rate members (lambda, T = hours), one beta group g1."""
    rate = W.rate(lam, hours)
    tree = M.top([M.gate("G1", "AND", [M.leaf(m, 0.0, name="Pump " + m, quant=rate) for m in "AB"],
                         name="Pumps fail")])
    return M.document(tree, [M.group()])


def typed_group_status(api, lam, hours=1000.0):
    """The status of group g1 of the document with this lambda typed into both members (the oracle)."""
    api.open_doc(rate_group_doc(lam, hours))
    status, body = api.get("/api/ccf/groups")
    assert status == 200, body
    (group,) = body["groups"]
    return group["status"]


def test_r1_a_rate_member_whose_raw_q_is_just_below_one_is_high_q_not_q_one(api):
    """lambda*T = 30 after the factor: raw q = 1 - 9.4e-14 (below 1), which the engine rounds to 1.0. The
    typed document keeps the group applied with CCF_HIGH_Q; "the group would not be applied" would be false."""
    import math

    from fta_web import engine

    lam, factor = 3e-3, 10                       # nominal lambda*T = 3, what-if lambda*T = 30
    scaled = factor * lam
    raw = -math.expm1(-scaled * 1000.0)
    assert raw < 1.0 and engine._tidy(raw) == 1.0          # the premise: the two readings differ
    body = ask(api, rate_group_doc(lam), {"A": factor})
    assert [r["clamped"] for r in body["events"]] == [False, False]
    assert body["events"][0]["q"] == raw < 1.0
    assert codes_of(body) == ["CCF_HIGH_Q"]
    assert entry_of(body, "CCF_HIGH_Q")["groupIds"] == ["g1"]

    status = typed_group_status(api, scaled)               # the oracle: ccf.assess on the typed document
    assert status["applied"] is True and status["code"] != "CCF_Q_ONE"
    assert "CCF_HIGH_Q" in [w["code"] for w in status.get("warnings") or []]


def test_r2_a_rate_member_whose_raw_q_is_one_is_q_one(api):
    """lambda*T = 38: raw q = 1 - 3e-17 is 1.0 in a float. Typed, the group is refused with CCF_Q_ONE."""
    import math

    lam, factor = 3.8e-3, 10
    scaled = factor * lam
    raw = -math.expm1(-scaled * 1000.0)
    assert raw == 1.0
    body = ask(api, rate_group_doc(lam), {"A": factor})
    assert [r["clamped"] for r in body["events"]] == [False, False]        # exactly 1, not above
    assert codes_of(body) == ["CCF_Q_ONE"]
    assert entry_of(body, "CCF_Q_ONE")["groupIds"] == ["g1"]

    status = typed_group_status(api, scaled)
    assert status["applied"] is False and status["code"] == "CCF_Q_ONE"


@pytest.mark.parametrize("delta, expected", [(1e-14, ["CCF_HIGH_Q"]), (-1e-16, [])])
def test_r3_a_rate_member_a_hair_around_the_high_q_limit_follows_the_raw_q(api, delta, expected):
    """Raw q = 0.01 + 1e-14 is above ccf.HIGH_Q for the typed document, while the 12-digit q is 0.01
    exactly (not above): the caution must say HIGH_Q. Raw q = 0.01 - 1e-16 is below it either way (and rounds to 0.01 too)."""
    import math

    from fta_web import ccf, engine

    hours, factor = 1000.0, 10
    target = ccf.HIGH_Q + delta
    lam = -math.log1p(-target) / hours / factor           # lambda' = factor * lam gives raw q about `target`
    scaled = factor * lam
    raw = -math.expm1(-scaled * hours)
    assert (raw > 0.01) == (delta > 0) and engine._tidy(raw) == 0.01       # the premise
    body = ask(api, rate_group_doc(lam, hours), {"A": factor})
    assert body["events"][0]["q"] == raw
    assert codes_of(body) == expected

    status = typed_group_status(api, scaled, hours)       # the oracle
    assert status["applied"] is True
    assert ("CCF_HIGH_Q" in [w["code"] for w in status.get("warnings") or []]) == bool(expected)


# ---------------------------------------------------------------- N: CCF_NOT_APPLIED (Y3, CR-20261104)
#
# A factor other than 1 on a member of a CCF group that is not applied at baseline (whatever the reason) gives
# ``{"code": "CCF_NOT_APPLIED", "groupIds": [...]}`` (group ids in document order, each once, no ``limit``).
# FR DESIGN 10.2: the single test is ``applied``; a factor of exactly 1, a non-member and an empty request give
# nothing; Q_ONE / HIGH_Q still read the applied groups only.


def na(*group_ids):
    return {"code": "CCF_NOT_APPLIED", "groupIds": list(group_ids)}


def pair_doc(a=1e-3, b=2e-3, d=1e-3, e=2e-3, groups=None):
    """OR [ G1 AND [A, B], G2 AND [D, E], Z ]: g1 on (A, B), g2 on (D, E), by default both differing."""
    tree = M.top([M.gate("G1", "AND", [M.pump("A", a), M.pump("B", b)], name="Pumps fail"),
                  M.gate("G2", "AND", [M.pump("D", d), M.pump("E", e)], name="Valves fail"),
                  M.leaf("Z", 1e-3, name="Sensor Z")])
    return M.document(tree, groups or [M.group(), M.group("g2", "Valves", members=("D", "E"))])


def test_n1_a_beta_group_that_is_not_applied_gives_the_caution_and_no_group_rows(api):
    """The old H7 case as a positive: members differ, factor 2 on A."""
    body = ask(api, W.unapplied_group_doc(), {"A": 2})
    assert cautions_of(body) == [NOT_APPLIED_G1]
    assert body["groups"] == []
    assert [(r["id"], r["viaGroup"], r["groupId"]) for r in body["events"]] == [("A", False, None)]
    assert "limit" not in entry_of(body, "CCF_NOT_APPLIED")
    json.dumps(body["cautions"])


def test_n1_the_other_member_and_both_members_give_the_same_entry(api):
    api.open_doc(W.unapplied_group_doc())
    for factors in ({"B": 3}, {"A": 2, "B": 3}, {"A": 0.5}, {"A": 2, "C": 5}):
        body = api.whatif_ok(factors)
        assert cautions_of(body) == [NOT_APPLIED_G1], factors
        assert all(r["viaGroup"] is False and r["groupId"] is None for r in body["events"]), factors


def test_n2_no_group_applied_at_all_the_plan_none_path(api):
    """Both members at Q = 1 (CCF_Q_ONE at baseline: not applied, so there is no plan at all). The
    number is the members scaled alone, exactly the answer of the same tree with no group stored."""
    tree = M.top([M.gate("G1", "AND", [M.pump("A", 1.0), M.pump("B", 1.0)], name="Pumps fail")])
    grouped = ask(api, M.document(tree, [M.group()]), {"A": 0.5})
    assert cautions_of(grouped) == [NOT_APPLIED_G1]
    assert grouped["groups"] == []
    assert grouped["method"] == "treeWalk"
    assert grouped["baseline"] == W.rel(1.0, 1e-12) and grouped["whatIf"] == W.rel(0.5, 1e-12)
    assert grouped["ratio"] == W.rel(0.5, 1e-12)
    assert [(r["id"], r["viaGroup"], r["groupId"], r["q"]) for r in grouped["events"]] == [("A", False, None, 0.5)]

    plain = ask(api, M.document(tree, None), {"A": 0.5})
    assert cautions_of(plain) == []                         # no group stored: nothing to say
    for key in ("method", "baseline", "whatIf", "ratio", "note", "truncatedBy", "groups", "events"):
        assert grouped[key] == plain[key], key              # the caution changes no number


def test_n2_every_group_bad_for_a_different_reason_is_the_same_path(api):
    """g1 (members differ) and g2 (one member): neither is applied; a factor on a member of either fires."""
    tree = M.top([M.gate("G1", "AND", [M.pump("A", 1e-3), M.pump("B", 2e-3)], name="Pumps fail"),
                  M.pump("D", 1e-3)])
    api.open_doc(M.document(tree, [M.group(), M.group("g2", "Lonely", members=("D",))]))
    assert cautions_of(api.whatif_ok({"A": 2})) == [na("g1")]
    assert cautions_of(api.whatif_ok({"D": 2})) == [na("g2")]
    assert cautions_of(api.whatif_ok({"D": 2, "A": 2})) == [na("g1", "g2")]
    assert api.whatif_ok({"A": 2})["groups"] == []


def test_n3_no_factor_on_a_member_no_caution(api):
    api.open_doc(W.unapplied_group_doc())
    for factors in ({}, {"A": 1}, {"B": 1}, {"A": 1, "B": 1}, {"C": 5}, {"C": 5, "A": 1}):
        assert cautions_of(api.whatif_ok(factors)) == [], factors


def test_n4_an_applied_and_a_not_applied_group_asked_together(api):
    """g1 is applied (A, B equal), g2 is not (D, E differ). The error / warning is g1's, the new entry
    is g2's, and the new entry comes first. Group-mate rows (viaGroup) are g1's only."""
    cases = [(0.5, {"A": 2, "D": 3}, "CCF_Q_ONE"), (0.05, {"A": 1.2, "D": 3}, "CCF_HIGH_Q"),
             (1e-3, {"A": 2, "D": 3}, None)]
    for q, factors, other in cases:
        body = ask(api, pair_doc(a=q, b=q), factors)
        expected = ["CCF_NOT_APPLIED"] + ([other] if other else [])
        assert codes_of(body) == expected, (q, factors)
        assert entry_of(body, "CCF_NOT_APPLIED")["groupIds"] == ["g2"]
        if other:
            assert entry_of(body, other)["groupIds"] == ["g1"]
        assert [g["id"] for g in body["groups"]] == ["g1"]
        by_id = {r["id"]: r for r in body["events"]}
        assert sorted(by_id) == ["A", "B", "D"]
        assert (by_id["A"]["viaGroup"], by_id["A"]["groupId"]) == (False, "g1")
        assert (by_id["B"]["viaGroup"], by_id["B"]["groupId"]) == (True, "g1")
        assert (by_id["D"]["viaGroup"], by_id["D"]["groupId"]) == (False, None)
        assert "g2" not in [i for c in cautions_of(body) if c["code"] != "CCF_NOT_APPLIED"
                            for i in c.get("groupIds", [])]


def test_n4_independent_of_each_other(api):
    """Only the applied group asked: no new entry. Only the not-applied one: no Q_ONE / HIGH_Q. The
    not-applied member at factor 1 next to a scaled applied group: no new entry."""
    api.open_doc(pair_doc(a=0.5, b=0.5))
    assert codes_of(api.whatif_ok({"A": 2})) == ["CCF_Q_ONE"]
    assert codes_of(api.whatif_ok({"A": 2, "D": 1})) == ["CCF_Q_ONE"]
    assert codes_of(api.whatif_ok({"D": 3})) == ["CCF_NOT_APPLIED"]
    assert codes_of(api.whatif_ok({"A": 1, "D": 3})) == ["CCF_NOT_APPLIED"]
    assert codes_of(api.whatif_ok({"A": 1, "D": 1})) == []


def test_n5_two_not_applied_groups_in_document_order_once_each(api):
    api.open_doc(pair_doc())
    status, reverse = api.raw_with('{"E": 2, "A": 2}')                 # the request names g2's member first
    assert status == 200, reverse
    assert cautions_of(reverse) == [na("g1", "g2")]
    assert cautions_of(api.whatif_ok({"A": 2, "B": 2, "D": 2, "E": 2})) == [na("g1", "g2")]   # once each
    assert cautions_of(api.whatif_ok({"E": 2})) == [na("g2")]
    assert cautions_of(api.whatif_ok({"B": 2})) == [na("g1")]


def test_n5_a_repeated_group_id_is_listed_once(api):
    """Two stored groups with the id g1 (a not-applied reason of its own): the id appears once."""
    groups = [M.group(), M.group("g1", "Valves", members=("D", "E"))]
    api.open_doc(pair_doc(a=1e-3, b=1e-3, d=1e-3, e=1e-3, groups=groups))     # equal members: only the id is wrong
    body = api.whatif_ok({"E": 2, "A": 2})
    assert cautions_of(body) == [na("g1")]
    assert body["groups"] == []


def test_n5_a_group_without_an_id_fires_with_no_id(api):
    """The trigger does not need an id; the id list may be empty for this code only (the caller invents none)."""
    nameless = M.group()
    del nameless["id"]
    api.open_doc(pair_doc(a=1e-3, b=1e-3, groups=[nameless]))
    body = api.whatif_ok({"A": 2})
    assert body["groups"] == []
    assert cautions_of(body) == [na()]
    assert cautions_of(api.whatif_ok({"A": 1})) == []
    api.open_doc(pair_doc(a=1e-3, b=1e-3, groups=[nameless, M.group("g2", "Valves", members=("D", "E"))]))
    assert cautions_of(api.whatif_ok({"A": 2})) == [na()]
    assert cautions_of(api.whatif_ok({"A": 2, "D": 2})) == [na("g2")]        # the nameless group adds no id
    assert cautions_of(api.whatif_ok({"D": 1.5, "A": 2})) == [na("g2")]
    assert cautions_of(api.whatif_ok({"D": 1.5})) == [na("g2")]


def test_n6_a_member_in_two_groups_lists_both(api):
    """A, B in g1 and B, C in g2: the assessment marks both groups not applied (CCF_MEMBER_IN_TWO_GROUPS)."""
    tree = M.top([M.gate("G1", "AND", [M.pump("A"), M.pump("B"), M.pump("C")], name="Pumps fail")])
    api.open_doc(M.document(tree, [M.group(), M.group("g2", "Valve group", members=("B", "C"))]))
    assert cautions_of(api.whatif_ok({"B": 2})) == [na("g1", "g2")]
    assert cautions_of(api.whatif_ok({"A": 2})) == [na("g1")]
    assert cautions_of(api.whatif_ok({"C": 2})) == [na("g2")]
    status, reverse = api.raw_with('{"C": 2, "A": 2}')
    assert status == 200, reverse
    assert cautions_of(reverse) == [na("g1", "g2")]
    assert api.whatif_ok({"B": 2})["groups"] == []


@pytest.mark.parametrize("kind", ["sum", "length", "size", "no_testing", "range"])
def test_n7_an_alpha_group_that_is_not_applied_fires(api, kind):
    """Alpha sum off by more than the tolerance, a list of the wrong length, five members, no testing
    scheme, an alpha outside 0 to 1."""
    members = "ABC"
    alpha, testing = [0.9, 0.06, 0.04], "staggered"
    if kind == "sum":
        alpha = [0.5, 0.2, 0.1]
    elif kind == "length":
        alpha = [0.6, 0.4]
    elif kind == "range":
        alpha = [1.5, -0.3, -0.2]
    elif kind == "no_testing":
        testing = None
    elif kind == "size":
        members, alpha = "ABCDE", [0.2] * 5
    tree = M.top([M.gate("G1", "AND", [M.pump(m, 0.005) for m in members], name="Pumps fail")])
    group = M.group(model="alpha", beta=None, alpha=alpha, testing=testing, members=tuple(members))
    body = ask(api, M.document(tree, [group]), {"A": 2.0000001})
    assert body["groups"] == []
    assert cautions_of(body) == [NOT_APPLIED_G1]
    # the same group, repaired, is applied and gives the HIGH_Q caution of H3 instead
    good = M.group(model="alpha", beta=None, alpha=[0.9, 0.06, 0.04], testing="staggered", members=("A", "B", "C"))
    tree3 = M.top([M.gate("G1", "AND", [M.pump(m, 0.005) for m in "ABC"], name="Pumps fail")])
    assert codes_of(ask(api, M.document(tree3, [good]), {"A": 2.0000001})) == ["CCF_HIGH_Q"]


def test_n8_with_cut_set_and_standby_cautions_three_entries_in_caution_order(api):
    """g1 on (B, C) differing; S standby scaled past lambda*tau 0.2; maxOrder 1 on a repeated-event tree."""
    tree = M.gate("root", "AND", [
        M.gate("G1", "OR", [M.leaf("A", 0.01, name="Event A"), M.leaf("B", 0.1, name="Event B"),
                            standby_event("S", 0.05, 2.0)], name="Branch 1"),
        M.gate("G2", "OR", [
            M.leaf("X", 0.0, name="Event X", links=[{"target_id": "A", "relation": "OR"}]),
            M.leaf("C", 0.2, name="Event C")], name="Branch 2"),
    ], name="Top event", type_="Root")
    doc = M.document(tree, [M.group(members=("B", "C"))], analysis={"cutsets": {"maxOrder": 1}})
    body = ask(api, doc, {"B": 2, "S": 2.0000001})
    assert body["method"] == "mcub" and "order" in body["truncatedBy"]            # the premises
    assert codes_of(body) == ["CCF_NOT_APPLIED", "STANDBY_LARGE_LT", "CUTSETS_TRUNCATED"]
    assert entry_of(body, "CCF_NOT_APPLIED")["groupIds"] == ["g1"]
    assert entry_of(body, "STANDBY_LARGE_LT")["eventIds"] == ["S"]
    assert entry_of(body, "CUTSETS_TRUNCATED")["by"] == ["order"]
    # the same request without the factor on B: no new entry, the other two stay
    assert codes_of(api.whatif_ok({"S": 2.0000001})) == ["STANDBY_LARGE_LT", "CUTSETS_TRUNCATED"]


def test_n9_cache_the_slot_is_built_once_and_the_caution_follows_the_request(api):
    from fta_web import whatif

    api.open_doc(W.unapplied_group_doc())
    first = api.whatif_ok({"A": 2})
    entry = whatif._cache
    assert entry is not None
    assert [(gid, tuple(members)) for gid, members in entry.unapplied] == [("g1", ("A", "B"))]
    kept = entry.unapplied
    silent = api.whatif_ok({"A": 1})
    again = api.whatif_ok({"A": 2})
    other = api.whatif_ok({"B": 3})
    assert [first["cache"], silent["cache"], again["cache"], other["cache"]] == ["miss", "hit", "hit", "hit"]
    assert codes_of(first) == ["CCF_NOT_APPLIED"] and cautions_of(silent) == []
    assert again["cautions"] == first["cautions"] == other["cautions"]
    assert whatif._cache is entry and entry.unapplied is kept and len(kept) == 1       # never written afterwards
    for body in (first, silent, again, other):            # the slot changes nothing else
        assert body["groups"] == [] and body["method"] == "treeWalk"
    assert entry.plan is None                              # plan stays None unless a group is applied (DESIGN 10.3)


def test_n9_the_slot_for_documents_without_a_not_applied_group(api):
    from fta_web import whatif

    api.open_doc(W.r1_doc())                               # the group is applied
    body = api.whatif_ok({"A": 10})
    assert whatif._cache.unapplied == [] and whatif._cache.plan is not None
    assert [g["id"] for g in body["groups"]] == ["g1"] and body["method"] == "mcub"
    api.open_doc(W.repeated_doc())                         # no group at all
    assert api.whatif_ok({"A": 10})["groups"] == []
    assert whatif._cache.unapplied == [] and whatif._cache.plan is None
    api.open_doc(pair_doc(a=0.5, b=0.5))                   # one applied, one not
    api.whatif_ok({"A": 2})
    assert [(gid, tuple(m)) for gid, m in whatif._cache.unapplied] == [("g2", ("D", "E"))]
    assert whatif._cache.plan is not None


# ---- N10: the typed oracle ------------------------------------------------------------------------------------
#
# Random documents over every reason a group is not applied. The reference is ``ccf.build_plan(...).assessments``
# worked out HERE from the loaded document (never through whatif.py), and ``ccf.assess`` on the same inputs must
# agree on ``applied``. Expected: CCF_NOT_APPLIED iff some id with a factor != 1 is a member of an assessment with
# ``applied`` False; its groupIds are those groups' ids in assessment order, each once (a group with no id adds none).
# The other codes of these documents (no standby, no cut-set limit) are the old rules: CCF_Q_ONE / CCF_HIGH_Q over the
# APPLIED groups only, from the member q times the factor, compared with >= 1.0 and > 0.01.

N10_DOCUMENTS = 300
N10_SEED = 20261104
N10_REASONS = [
    "clean", "too_few_one", "too_few_none", "not_basic_gate", "not_basic_missing", "renamed", "two_groups",
    "bad_beta", "bad_model", "alpha_sum", "alpha_length", "alpha_size", "no_testing", "no_probability",
    "members_differ", "q_one", "event_id", "reserved", "no_id", "dup_id",
]
#: (code, kind) of the findings that must each be seen in a not-applied group at least once, and fire at least once.
N10_REQUIRED_LABELS = {
    "CCF_TOO_FEW_MEMBERS/one", "CCF_TOO_FEW_MEMBERS/none", "CCF_MEMBER_NOT_BASIC/gate",
    "CCF_MEMBER_NOT_BASIC/missing", "CCF_MEMBER_RENAMED", "CCF_MEMBER_IN_TWO_GROUPS", "CCF_BAD_PARAMETER/beta",
    "CCF_BAD_PARAMETER/model", "CCF_BAD_PARAMETER/id", "CCF_BAD_PARAMETER/id:reserved",
    "CCF_BAD_PARAMETER/event_id", "CCF_ALPHA_SUM/length", "CCF_ALPHA_SUM/sum", "CCF_ALPHA_SIZE",
    "CCF_NO_TESTING/missing", "CCF_NO_PROBABILITY", "CCF_MEMBERS_DIFFER/parameter", "CCF_Q_ONE",
}


def n10_label(finding):
    kind = finding.kind
    if finding.code == "CCF_BAD_PARAMETER" and kind == "id" and finding.params.get("reserved"):
        kind = "id:reserved"
    return finding.code + ("/" + kind if kind else "")


def n10_document(rng, reason):
    """``(document, the reason of the first group)``: 4-8 basic events (fixed q) under AND / OR gates G1..Gk and 1-3
    stored groups; the first group is drawn from ``reason``, the others at random."""
    n = rng.randint(5, 8)
    ids = ["E%d" % i for i in range(n)]
    qs = {i: rng.choice([1e-3, 2e-3, 5e-3, 0.02, 0.1]) for i in ids}
    pool = []
    extra_leaves = []                    # (leaf node,) added under G1
    no_probability = set()

    def take(count):
        out = []
        while len(out) < count:
            if not pool:
                pool.extend(ids)
                rng.shuffle(pool)
            member = pool.pop()
            if member not in out:
                out.append(member)
        return out

    def equal(members, q=None):
        q = q if q is not None else rng.choice([1e-3, 5e-3, 0.02, 0.3])
        for member in members:
            qs[member] = q

    def beta_group(gid, members, **over):
        return M.group(gid, "Group " + gid, members=members, beta=rng.choice([0.05, 0.1, 0.3]), **over)

    def alpha_group(gid, members, alpha=None, testing="staggered", **over):
        alpha = alpha if alpha is not None else {2: [0.9, 0.1], 3: [0.9, 0.06, 0.04]}[len(members)]
        return M.group(gid, "Group " + gid, model="alpha", beta=None, alpha=alpha, testing=testing,
                       members=members, **over)

    def make(kind, gid):
        """The list of stored groups this kind adds (two for the two-group reasons)."""
        if kind == "clean":
            if rng.random() < 0.3:
                members = take(rng.choice([2, 3]))
                equal(members)
                return [alpha_group(gid, members, testing=rng.choice(["staggered", "nonStaggered"]))]
            members = take(rng.choice([2, 3]))
            equal(members)
            return [beta_group(gid, members)]
        if kind == "too_few_one":
            return [beta_group(gid, take(1))]
        if kind == "too_few_none":
            return [beta_group(gid, [])]
        if kind == "not_basic_gate":
            members = take(1) + ["G1"]
            return [beta_group(gid, members)]
        if kind == "not_basic_missing":
            return [beta_group(gid, take(1) + ["ghost"])]
        if kind == "renamed":
            members = take(2)
            equal(members)
            extra_leaves.append(members[0])                  # a second node with this id: the loader renames one
            return [beta_group(gid, members)]
        if kind == "two_groups":
            first = take(2)
            equal(first)
            other = take(1)
            while other[0] in first:
                other = take(1)
            return [beta_group(gid, first), beta_group(gid + "b", [first[1], other[0]])]
        if kind == "bad_beta":
            members = take(2)
            equal(members)
            return [M.group(gid, "Group " + gid, members=members, beta=rng.choice([1.5, -0.1, "abc", None, True]))]
        if kind == "bad_model":
            members = take(2)
            equal(members)
            return [beta_group(gid, members, model="gamma")]
        if kind in ("alpha_sum", "alpha_length", "no_testing"):
            members = take(3)
            equal(members)
            if kind == "alpha_sum":
                return [alpha_group(gid, members, alpha=[0.5, 0.2, 0.1])]
            if kind == "alpha_length":
                return [alpha_group(gid, members, alpha=[0.6, 0.4])]
            return [alpha_group(gid, members, testing=None)]
        if kind == "alpha_size":
            members = take(5)
            equal(members)
            return [alpha_group(gid, members, alpha=[0.2] * 5)]
        if kind == "no_probability":
            members = take(2)
            equal(members)
            no_probability.add(members[1])
            return [beta_group(gid, members)]
        if kind == "members_differ":
            members = take(2)
            qs[members[0]], qs[members[1]] = 1e-3, 3e-3
            return [beta_group(gid, members)]
        if kind == "q_one":
            members = take(2)
            equal(members, 1.0)
            return [beta_group(gid, members)]
        if kind == "event_id":
            members = take(2)
            equal(members)
            others = take(2)
            equal(others)
            # alpha "ga" on (X, Y) makes ccf:ga:X+Y; beta "ga:X+Y" makes the same id
            return [alpha_group("ga", members), beta_group("ga:%s+%s" % tuple(members), others)]
        if kind == "reserved":
            members = take(2)
            equal(members)
            extra_leaves.append("ccf:x")
            return [beta_group(gid, members)]
        if kind == "no_id":
            members = take(2)
            equal(members)
            group = beta_group(gid, members)
            del group["id"]
            return [group]
        if kind == "dup_id":
            first, second = take(2), take(2)
            equal(first)
            equal(second)
            return [beta_group("g1", first), beta_group("g1", second)]
        raise AssertionError(kind)

    groups = make(reason, "g1")
    wanted = rng.randint(1, 3)
    while len(groups) < wanted:
        kind = rng.choice(["clean", "clean", "clean", "members_differ", "too_few_one", "bad_beta", "q_one"])
        groups.extend(make(kind, "g%d" % (len(groups) + 1)))

    shuffled = list(ids)
    rng.shuffle(shuffled)
    gate_count = rng.randint(1, min(3, n // 2))
    buckets = [shuffled[i::gate_count] for i in range(gate_count)]
    gates = []
    for index, bucket in enumerate(buckets):
        leaves = []
        for member in bucket:
            quant = {"model": "rate"} if member in no_probability else None
            leaves.append(M.leaf(member, 0.0 if quant else qs[member], name="Event " + member, quant=quant))
        if index == 0:
            for extra in extra_leaves:
                leaves.append(M.leaf(extra, qs.get(extra, 1e-3), name="Twin of " + extra))
        gates.append(M.gate("G%d" % (index + 1), rng.choice(["AND", "OR"]), leaves, name="Gate %d" % (index + 1)))
    # no order / cutoff truncation: CUTSETS_TRUNCATED must stay out of these documents (the old rules)
    return M.document(M.top(gates), groups, analysis={"cutsets": {"maxOrder": 10, "maxCount": 5000, "cutoff": 0.0}})


def n10_reference():
    """``(assessments, applied group ids in plan order)`` of the document the app has open, worked out with
    ``ccf`` directly; ``ccf.assess`` on the same inputs must agree on ``applied``."""
    import copy

    from fta_web import ccf, logic
    from fta_web.state import get_state

    state = get_state()
    with state.lock:
        tree = copy.deepcopy(state.core.get_data())
        analysis = copy.deepcopy(state.core.analysis)
    core = logic.recalculated_core(tree, analysis)
    raw = ccf.groups_of(analysis)
    renamed = analysis.get(ccf.RENAMED_KEY)
    plan = ccf.build_plan(raw, renamed, core.get_data(), core.analysis)
    merged = dict(core.analysis)
    if isinstance(renamed, dict) and renamed:
        merged[ccf.RENAMED_KEY] = renamed
    typed = ccf.assess(raw, core.get_data(), merged)
    assert plan is not None
    assert [a.applied for a in typed] == [a.applied for a in plan.assessments]
    return plan.assessments, [g.id for g in plan.groups], tree


def n10_leaf_ids(tree):
    """Basic events of the open document as the Grid reads them (first node of an id; not the root, not a house
    event, not a transfer) and whether each is evaluable (a rate event without a lambda is not)."""
    found = {}
    for node in W.walk(tree):
        key = str(node.get("id"))
        if key in found:
            continue
        basic = (node is not tree and not node.get("children")
                 and str(node.get("eventKind") or "").lower() != "house"
                 and str(node.get("gateType") or "").upper() != "TRANSFER")
        found[key] = (node, basic)
    return {k: node for k, (node, basic) in found.items() if basic}


def n10_expected(assessments, applied_ids, tree, factors):
    """``[NOT_APPLIED?, Q_ONE?, HIGH_Q?]`` entries by the rules of DESIGN 10.2 and 1.3, from the reference alone."""
    out = []
    scaled = {m for m, f in factors.items() if f != 1}
    hit = [a for a in assessments if not a.applied and scaled & set(a.members)]
    if hit:
        ids = []
        for a in hit:
            if a.id is not None and a.id not in ids:
                ids.append(a.id)
        out.append(na(*ids))
    leaves = n10_leaf_ids(tree)
    one, high = [], []
    for a in assessments:
        if not a.applied:
            continue
        asked = [m for m in a.members if factors.get(m, 1) != 1]
        if not asked:
            continue
        factor = factors[asked[0]]
        raw = [min(1.0, factor * float(leaves[m]["probability"])) for m in a.members]
        if any(q >= 1.0 for q in raw):
            one.append(a.id)
        elif max(raw) > HIGH_Q:
            high.append(a.id)
    if one:
        out.append({"code": "CCF_Q_ONE", "groupIds": one})
    if high:
        out.append({"code": "CCF_HIGH_Q", "groupIds": high, "limit": HIGH_Q})
    return out


def test_n10_the_typed_oracle_over_random_documents(api):
    import random

    rng = random.Random(N10_SEED)
    seen_labels = {}                 # label -> documents that have it in a not-applied group
    fired_labels = {}                # label -> documents where a factored member of such a group made the caution fire
    fire = silent = no_plan = mixed = 0
    for index in range(N10_DOCUMENTS):
        reason = N10_REASONS[index % len(N10_REASONS)]
        doc = n10_document(rng, reason)
        api.open_doc(doc)
        assessments, applied_ids, tree = n10_reference()
        leaves = n10_leaf_ids(tree)
        member_leaves = [m for a in assessments for m in a.members if m in leaves]
        chosen = []
        for _ in range(rng.randint(1, 4)):
            pick = rng.choice(member_leaves) if member_leaves and rng.random() < 0.7 else rng.choice(sorted(leaves))
            if pick not in chosen:
                chosen.append(pick)
        factors = {m: rng.choice([1, 0.5, 2]) for m in chosen}
        for m in chosen:                                         # a rate event with no lambda cannot be scaled
            if (leaves[m].get("quant") or {}).get("model") == "rate":
                factors[m] = 1
        for a in assessments:                                    # one factor per applied group (else group_conflict)
            if a.applied:
                asked = [m for m in a.members if m in factors]
                for m in asked:
                    factors[m] = factors[asked[0]]

        body = api.whatif_ok(factors)
        where = "document %d (%s), factors %s" % (index, reason, factors)
        expected = n10_expected(assessments, applied_ids, tree, factors)
        assert cautions_of(body) == expected, where
        assert [g["id"] for g in body["groups"]] == applied_ids, where
        for item in cautions_of(body):
            if item["code"] in ("CCF_Q_ONE", "CCF_HIGH_Q"):
                assert set(item["groupIds"]) <= set(applied_ids), where      # never a not-applied group
        for row in body["events"]:
            if row["groupId"] is None:
                assert row["viaGroup"] is False, where                       # a not-applied member is never a group-mate
        assert all(a.id is None or a.id in [g.get("id") for g in doc["analysis"]["ccfGroups"]] for a in assessments), where

        fired = "CCF_NOT_APPLIED" in codes_of(body)
        fire += fired
        silent += not fired
        no_plan += not applied_ids
        mixed += bool(applied_ids) and any(not a.applied for a in assessments)
        scaled = {m for m, f in factors.items() if f != 1}
        for a in assessments:
            if a.applied:
                continue
            for label in {n10_label(f) for f in a.findings if f.severity == "error"}:
                seen_labels[label] = seen_labels.get(label, 0) + 1
                if scaled & set(a.members):
                    fired_labels[label] = fired_labels.get(label, 0) + 1

    # coverage guard: the generator really drew every reason, and both outcomes, and both plan shapes
    missing = sorted(N10_REQUIRED_LABELS - set(seen_labels))
    assert not missing, "the generator never produced these not-applied reasons: %s (seen %s)" % (missing, sorted(seen_labels))
    #: a group with no members at all has nothing to put a factor on: it can never fire
    never_fired = sorted(N10_REQUIRED_LABELS - {"CCF_TOO_FEW_MEMBERS/none"} - set(fired_labels))
    assert not never_fired, "no document fired the caution through these reasons: %s" % never_fired
    assert fire >= 60 and silent >= 60, (fire, silent)
    assert no_plan >= 20, no_plan                      # the plan-is-None path (no group applied) is exercised
    assert mixed >= 20, mixed                          # an applied and a not-applied group in one document


# ---------------------------------------------------------------- D: CAUTION_ORDER is the order of the list


def test_d1_caution_order_is_the_list_order_of_the_design():
    from fta_web import whatif

    assert list(whatif.CAUTION_ORDER) == ORDER
    assert whatif.CAUTION_ORDER[0] == "CCF_NOT_APPLIED"          # the largest effect: the whole CCF is missing
    assert list(whatif.CAUTION_ORDER[1:]) == FOUR                # the other four keep their relative order


def test_d2_the_returned_list_follows_caution_order(api, monkeypatch):
    """The order of the list is whatif.CAUTION_ORDER read at call time: a build that writes the five
    ``if`` blocks in the right order by hand and ignores the constant fails the permuted run."""
    from fta_web import whatif

    api.open_doc(all_five_doc())
    body = api.whatif_ok(ALL_FIVE_FACTORS)
    assert codes_of(body) == [c for c in whatif.CAUTION_ORDER if c in codes_of(body)] == ORDER

    permuted = ("CUTSETS_TRUNCATED", "STANDBY_LARGE_LT", "CCF_NOT_APPLIED", "CCF_HIGH_Q", "CCF_Q_ONE")
    assert sorted(permuted) == sorted(ORDER) and list(permuted) != ORDER
    monkeypatch.setattr(whatif, "CAUTION_ORDER", permuted)
    api.open_doc(all_five_doc())                          # a new document: no cached baseline matters
    again = api.whatif_ok(ALL_FIVE_FACTORS)
    assert codes_of(again) == list(permuted)
    assert again["cautions"] != body["cautions"]
    assert sorted(codes_of(again)) == sorted(codes_of(body))


def test_d2_a_permuted_order_moves_only_the_not_applied_entry_when_it_alone_changes(api, monkeypatch):
    """The new code is an ordinary member of CAUTION_ORDER: put last, it is last."""
    from fta_web import whatif

    last = tuple(c for c in ORDER if c != "CCF_NOT_APPLIED") + ("CCF_NOT_APPLIED",)
    monkeypatch.setattr(whatif, "CAUTION_ORDER", last)
    api.open_doc(all_five_doc())
    assert codes_of(api.whatif_ok(ALL_FIVE_FACTORS)) == list(last)
