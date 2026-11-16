"""Integration of the what-if sliders (F4) with the alpha-factor CCF model (F2A):
PLAN section 6 (F2A + F4) and the post-merge list of the F4 engineering review.

Every case goes through ``POST /api/whatif`` on a real document opened through the
file route, with the Flask test client. The expected numbers are written out HERE,
from the sources, and nothing is taken from the product for them:

* NUREG/CR-5485 Eq. 5.6 (staggered testing), for a group of m identical members
  with alpha-factors alpha_1 .. alpha_m and total probability Q_t per member::

      Q_k = alpha_k / C(m-1, k-1) * Q_t

  Q_k is the probability of EACH CCF event that fails one given set of k members.
* NUREG/CR-5485 Eq. 5.7-5.9 (non-staggered testing)::

      alpha_t = sum_k k * alpha_k        Q_k = k / C(m-1, k-1) * alpha_k / alpha_t * Q_t

* FN-43: an alpha list whose sum is within 1e-3 of 1 is divided by its sum first.

The top event of AND[A, B, C] with an alpha group over A, B, C is then worked out by
hand: member i fails through its independent part i' (probability Q_1) or through any
CCF event whose member set contains i (probability Q_|S|). The cut sets are every way
of choosing one failure per member, with the sets that contain another set dropped;
the top event is the min-cut upper bound 1 - prod(1 - P(cut set)), the headline's
method. (As the editor treats the CCF events of a group as independent basic events,
cut sets with two overlapping CCF events are kept; this hand value keeps them too.)

A what-if factor on a member of an applied group multiplies the Q_t of EVERY member
(DESIGN 4.2), so after a factor f on one member each member has Q_t = f * q.
"""
import datetime
import itertools
import json
import math
import re
import statistics
import time
from pathlib import Path

import pytest

flask = pytest.importorskip("flask")

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
ARTIFACTS = REPO_ROOT / ".division" / "artifacts" / "perf"

Q = 1e-3
ALPHA = [0.95, 0.04, 0.01]
FACTOR = 10.0
MEMBERS = ["A", "B", "C"]

#: The numbers of the F4 engineering review (AND[A,B,C], q 1e-3, alpha (0.95, 0.04, 0.01),
#: factor 10 on B), written as literals so that a transcription error in the hand code shows.
LITERAL_STAGGERED = 1.0667669e-4
LITERAL_NON_STAGGERED = 2.9430865e-4


def close(expected, tol=1e-9):
    """``pytest.approx`` with exactly the stated relative tolerance (no absolute part)."""
    return pytest.approx(expected, rel=tol, abs=0)


# ---------------------------------------------------------------- the hand calculation


def hand_q_k(alpha, testing, qt):
    """``[Q_1 .. Q_m]``: Eq. 5.6 (staggered) or Eq. 5.7-5.9 (non-staggered), with the
    alphas divided by their sum first (FN-43)."""
    m = len(alpha)
    total = sum(alpha)
    a = [value / total for value in alpha]
    if testing == "staggered":
        return [a[k - 1] / math.comb(m - 1, k - 1) * qt for k in range(1, m + 1)]
    alpha_t = sum(k * a[k - 1] for k in range(1, m + 1))
    return [k / math.comb(m - 1, k - 1) * (a[k - 1] / alpha_t) * qt for k in range(1, m + 1)]


def hand_and_top(alpha, testing, qt):
    """The min-cut upper bound of AND[1..m] with the alpha model over all m members."""
    m = len(alpha)
    q_k = hand_q_k(alpha, testing, qt)
    probability = {}
    for i in range(m):
        probability[("ind", i)] = q_k[0]
    for size in range(2, m + 1):
        for subset in itertools.combinations(range(m), size):
            probability[("ccf", subset)] = q_k[size - 1]
    # member i fails through its own independent part or through a CCF event that holds i
    ways = [[("ind", i)] + [e for e in probability if e[0] == "ccf" and i in e[1]]
            for i in range(m)]
    candidates = {frozenset(choice) for choice in itertools.product(*ways)}
    minimal = [c for c in candidates if not any(other < c for other in candidates)]
    survive = 1.0
    for cut in minimal:
        survive *= 1.0 - math.prod(probability[event] for event in cut)
    return 1.0 - survive


# ---------------------------------------------------------------- documents


def _leaf(node_id, q):
    return {"id": node_id, "name": "Pump " + node_id, "type": "Event", "logicGate": "OR",
            "probability": q, "notes": "", "links": [], "children": [],
            "quant": {"model": "fixed"}}


def _alpha_group(members, alpha, testing, gid="g"):
    return {"id": gid, "name": "Valves", "model": "alpha", "beta": None, "alpha": list(alpha),
            "testing": testing, "members": list(members), "source": "test"}


def _document(children, groups, title="what-if integration"):
    tree = {"id": "root", "name": "Top event", "type": "Root", "logicGate": "AND",
            "probability": 1.0, "notes": "", "links": [], "children": children}
    return {"title": title, "date": "2026-11-02", "mode": "FTA", "fileFormatVersion": 2,
            "tree": tree, "analysis": {"ccfGroups": groups}}


def and_abc(alpha=ALPHA, testing="staggered"):
    """AND[A, B, C], fixed q 1e-3 each, one alpha group over A, B, C."""
    return _document([_leaf(m, Q) for m in MEMBERS], [_alpha_group(MEMBERS, alpha, testing)])


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


class Api:
    """The Flask test client with JSON in and out."""

    def __init__(self, client, root):
        self.client = client
        self.root = Path(root)

    def get(self, url):
        response = self.client.get(url)
        return response.status_code, response.get_json()

    def post(self, url, payload):
        response = self.client.post(url, json=payload)
        return response.status_code, response.get_json()

    def open_doc(self, doc, name="doc.json"):
        path = self.root / name
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        status, body = self.post("/api/file/open", {"path": str(path), "force": True})
        assert status == 200, body

    def headline(self):
        status, body = self.get("/api/analysis/summary")
        assert status == 200, body
        return body["headline"]

    def groups(self):
        status, body = self.get("/api/ccf/groups")
        assert status == 200, body
        return body["groups"]

    def whatif(self, factors):
        status, revision = self.get("/api/revision")
        assert status == 200, revision
        return self.post("/api/whatif", {"revision": revision["revision"],
                                         "documentSerial": revision["documentSerial"],
                                         "factors": factors})

    def whatif_ok(self, factors):
        status, body = self.whatif(factors)
        assert status == 200, (status, body)
        assert body["ok"] is True, body
        return body


@pytest.fixture
def api(tmp_path):
    from fta_web.routes.analysis import analysis_bp
    from fta_web.routes.ccf import ccf_bp
    from fta_web.routes.files import files_bp
    from fta_web.routes.tree import tree_bp
    from fta_web.routes.whatif import whatif_bp
    from fta_web.state import get_state, reset_state
    from fta_web import errors

    reset_state()
    app = flask.Flask(__name__)

    @app.errorhandler(errors.ApiError)
    def _handle(err):  # the real app registers the same handler
        return errors.api_error_response(err)

    for blueprint in (tree_bp, files_bp, analysis_bp, ccf_bp, whatif_bp):
        app.register_blueprint(blueprint)
    app.config.update(TESTING=True)
    get_state().fs_root = tmp_path
    with app.test_client() as client:
        yield Api(client, tmp_path)
    reset_state()


def row_of(body, node_id):
    rows = [r for r in body["events"] if r["id"] == node_id]
    assert len(rows) == 1, (node_id, [r["id"] for r in body["events"]])
    return rows[0]


# ---------------------------------------------------------------- 1. the review's numbers


def test_the_hand_code_itself_gives_the_review_numbers():
    """A check on the hand calculation before it is used as an oracle: every member has
    Q_t = 10 * 1e-3, the literals of the engineering review come out (rel 1e-7, abs 0)."""
    assert hand_and_top(ALPHA, "staggered", FACTOR * Q) == close(LITERAL_STAGGERED, 1e-7)
    assert hand_and_top(ALPHA, "nonStaggered", FACTOR * Q) == close(LITERAL_NON_STAGGERED, 1e-7)
    # Eq. 5.6 on the numbers of the case: Q_1 = 0.95 Qt, Q_2 = 0.04/2 Qt, Q_3 = 0.01 Qt
    assert hand_q_k(ALPHA, "staggered", 1e-2) == [pytest.approx(v, rel=1e-12, abs=0) for v in
                                                  (9.5e-3, 2e-4, 1e-4)]


@pytest.mark.parametrize("testing, literal", [("staggered", LITERAL_STAGGERED),
                                              ("nonStaggered", LITERAL_NON_STAGGERED)])
def test_factor_10_on_b_matches_the_hand_value_for_both_testing_schemes(api, testing, literal):
    api.open_doc(and_abc(testing=testing))
    body = api.whatif_ok({"B": FACTOR})
    assert body["method"] == "mcub"
    assert body["note"] is None and body["truncatedBy"] == []
    expected = hand_and_top(ALPHA, testing, FACTOR * Q)
    assert body["whatIf"] == close(expected, 1e-9)
    assert body["whatIf"] == close(literal, 1e-7)           # the literal of the review
    # the baseline is the same hand calculation at the nominal Q_t
    assert body["baseline"] == close(hand_and_top(ALPHA, testing, Q), 1e-9)
    assert body["baseline"] == api.headline()
    assert body["ratio"] == close(body["whatIf"] / body["baseline"], 1e-12)


# ---------------------------------------------------------------- 2. reset


@pytest.mark.parametrize("testing", ["staggered", "nonStaggered"])
def test_no_factor_gives_the_headline_exactly(api, testing):
    api.open_doc(and_abc(testing=testing))
    headline = api.headline()
    assert api.whatif_ok({"B": FACTOR})["whatIf"] != headline
    for factors in ({}, {"A": 1, "B": 1, "C": 1}, {"B": 1.0}):
        body = api.whatif_ok(factors)
        assert body["whatIf"] == headline            # the same float, not nearly
        assert body["baseline"] == headline
        assert body["ratio"] == 1.0
        assert all(row["factor"] == 1 and row["viaGroup"] is False for row in body["events"])


# ---------------------------------------------------------------- 3. CCF_ALPHA_NORMALISED


NORMALISED_ALPHA = [0.95, 0.04, 0.0105]       # sum 1.0005, inside the 1e-3 tolerance (FN-43)


@pytest.mark.parametrize("testing", ["staggered", "nonStaggered"])
def test_an_alpha_list_that_is_normalised_still_answers_and_scales(api, testing):
    api.open_doc(and_abc(alpha=NORMALISED_ALPHA, testing=testing))
    (group,) = api.groups()
    assert group["status"]["applied"] is True
    assert [w["code"] for w in group["status"]["warnings"]] == ["CCF_ALPHA_NORMALISED"]

    headline = api.headline()
    reset = api.whatif_ok({"A": 1})
    assert reset["whatIf"] == headline and reset["baseline"] == headline
    # the hand value divides the alphas by their sum (1.0005) before Eq. 5.6 / 5.7
    assert headline == close(hand_and_top(NORMALISED_ALPHA, testing, Q), 1e-9)

    body = api.whatif_ok({"C": 5})
    expected = hand_and_top(NORMALISED_ALPHA, testing, 5 * Q)
    assert body["whatIf"] == close(expected, 1e-9)
    assert row_of(body, "C")["viaGroup"] is False
    assert row_of(body, "A")["viaGroup"] is True and row_of(body, "A")["factor"] == 5


# ---------------------------------------------------------------- 4. a group refused for event_id


def _independent_or_of_ands(a, b, c, d):
    # 1 - (1 - ab)(1 - cd) without the cancellation of the plain subtraction (ab ~ 1e-6)
    return -math.expm1(math.log1p(-a * b) + math.log1p(-c * d))


def _clash_two_groups():
    """Alpha group g on a, b makes ccf:g:a+b; the beta group "g:a+b" on p, q makes it too: both
    groups are refused (FN-41, CR-20261102-event-id-refusal)."""
    tree_children = [
        {"id": "G1", "name": "Pair 1", "type": "Event", "logicGate": "AND", "probability": 1.0,
         "notes": "", "links": [], "children": [_leaf("a", Q), _leaf("b", Q)]},
        {"id": "G2", "name": "Pair 2", "type": "Event", "logicGate": "AND", "probability": 1.0,
         "notes": "", "links": [], "children": [_leaf("p", Q), _leaf("q", Q)]},
    ]
    doc = _document(tree_children, [
        _alpha_group(["a", "b"], [0.9, 0.1], "staggered", gid="g"),
        {"id": "g:a+b", "name": "Clash", "model": "beta", "beta": 0.1, "alpha": None,
         "testing": None, "members": ["p", "q"], "source": "test"}])
    doc["tree"]["logicGate"] = "OR"
    return doc


def _clash_inside_one_group():
    """Members a, b+c, a+b, c: the subsets {a, b+c} and {a+b, c} are both ccf:g:a+b+c."""
    ids = ["a", "b+c", "a+b", "c"]
    return _document([_leaf(i, Q) for i in ids],
                     [_alpha_group(ids, [0.7, 0.2, 0.06, 0.04], "staggered")])


def _assert_event_id_refusal(listing, event):
    """Every group of ``listing`` is refused for the event id ``event`` itself (kind event_id),
    not for another CCF_BAD_PARAMETER reason: the status reason names that id."""
    for group in listing:
        status = group["status"]
        assert status["reason"]["en"] == 'CCF event id "%s" would be made twice' % event, status
        assert event in status["message"]["en"] and event in status["message"]["ja"], status


def test_a_group_refused_for_its_event_id_is_not_applied_by_the_what_if_two_groups(api):
    api.open_doc(_clash_two_groups())
    listing = api.groups()
    assert [g["status"]["applied"] for g in listing] == [False, False]
    assert all(g["status"]["code"] == "CCF_BAD_PARAMETER" for g in listing)
    _assert_event_id_refusal(listing, "ccf:g:a+b")

    # NOTE: the rel 1e-12 checks below rely on short decimal inputs (1e-3, 10, 5): the engine
    # rounds a gate's probability, so a non-round q would differ from the hand value by more.
    headline = api.headline()
    assert headline == close(_independent_or_of_ands(Q, Q, Q, Q), 1e-12)
    body = api.whatif_ok({"a": FACTOR})
    assert body["groups"] == []                               # nothing is applied
    assert [r["id"] for r in body["events"]] == ["a"]         # no other member joins the row list
    row = body["events"][0]
    assert row["groupId"] is None and row["viaGroup"] is False and row["factor"] == FACTOR
    assert row["q"] == close(FACTOR * Q, 1e-12)               # a alone: b stays at its own q
    assert body["whatIf"] == close(_independent_or_of_ands(FACTOR * Q, Q, Q, Q), 1e-12)
    assert body["baseline"] == headline

    # the member of the other refused (beta) group is independent as well
    other = api.whatif_ok({"p": FACTOR})
    assert other["groups"] == []
    assert [r["id"] for r in other["events"]] == ["p"]
    assert other["whatIf"] == close(_independent_or_of_ands(Q, Q, FACTOR * Q, Q), 1e-12)
    # two different factors in the (refused) group are not a conflict: they are independent
    both = api.whatif_ok({"a": 10, "b": 5})
    assert both["whatIf"] == close(_independent_or_of_ands(10 * Q, 5 * Q, Q, Q), 1e-12)


def test_a_group_refused_for_its_event_id_is_not_applied_by_the_what_if_one_group(api):
    api.open_doc(_clash_inside_one_group())
    (group,) = api.groups()
    assert group["status"]["applied"] is False
    assert group["status"]["code"] == "CCF_BAD_PARAMETER"
    _assert_event_id_refusal([group], "ccf:g:a+b+c")

    body = api.whatif_ok({"a": FACTOR})
    assert body["groups"] == []
    assert [r["id"] for r in body["events"]] == ["a"]
    assert body["events"][0]["viaGroup"] is False and body["events"][0]["groupId"] is None
    # AND of four independent events: the product, only "a" scaled
    assert body["whatIf"] == close(FACTOR * Q * Q ** 3, 1e-12)
    assert body["baseline"] == close(Q ** 4, 1e-12)
    # an id with "+" is an ordinary basic event for the what-if
    assert api.whatif_ok({"b+c": 100})["whatIf"] == close(100 * Q * Q ** 3, 1e-12)


# ---------------------------------------------------------------- 5. F2A + F4: a member scales all


@pytest.mark.parametrize("testing", ["staggered", "nonStaggered"])
def test_a_factor_on_one_alpha_member_scales_every_member(api, testing):
    api.open_doc(and_abc(testing=testing))
    body = api.whatif_ok({"B": FACTOR})
    assert [r["id"] for r in body["events"]] == ["B", "A", "C"]     # requested first, then group order
    assert [r["viaGroup"] for r in body["events"]] == [False, True, True]
    for row in body["events"]:
        assert row["groupId"] == "g"
        assert row["factor"] == FACTOR
        assert row["paramKey"] == "q" and row["evaluable"] is True and row["clamped"] is False
        assert row["nominalQ"] == close(Q, 1e-12)
        assert row["q"] == close(FACTOR * Q, 1e-12)                # Q_t of the member, scaled
        assert row["param"] == close(FACTOR * Q, 1e-12)
    assert body["groups"] == [{"id": "g", "name": "Valves", "model": "alpha", "members": MEMBERS}]

    expected = hand_and_top(ALPHA, testing, FACTOR * Q)
    # the same factor asked on any one member gives the same group and the same top event
    for member in MEMBERS:
        other = api.whatif_ok({member: FACTOR})
        assert other["whatIf"] == close(expected, 1e-9)
        assert row_of(other, member)["viaGroup"] is False
        assert sorted(r["id"] for r in other["events"]) == MEMBERS
    # one member at 10 and another at 1 means a group factor of 10; two different factors conflict
    assert api.whatif_ok({"A": FACTOR, "C": 1})["whatIf"] == close(expected, 1e-9)
    status, error = api.whatif({"A": 10, "C": 5})
    assert status == 400 and error["error"]["detail"]["reason"] == "group_conflict"


# ---------------------------------------------------------------- 6. PERF-8 (alpha fixture)


PERF_BOUND_MS = 300.0
PERF_CALLS = 5
PERF_EVENT = "C0_1_0"         # a member of the alpha group A1 of perf_alpha_301.json
ABSOLUTE_PATH = re.compile(r"[A-Za-z]:[\\/]|\\\\|/Users/|/home/|/tmp/|/var/")


def test_perf_8_the_median_what_if_on_the_alpha_fixture_answers_within_the_bound(api):
    doc = json.loads((FIXTURES / "perf_alpha_301.json").read_text(encoding="utf-8"))
    api.open_doc(doc)
    status, revision = api.get("/api/revision")
    payload = {"revision": revision["revision"], "documentSerial": revision["documentSerial"],
               "factors": {PERF_EVENT: FACTOR}}

    status, first = api.post("/api/whatif", payload)               # the warm-up: builds the baseline
    assert status == 200 and first["cache"] == "miss", (status, first)
    runs_ms = []
    for _ in range(PERF_CALLS):                                    # the timed calls (cache hits)
        started = time.perf_counter()
        status, second = api.post("/api/whatif", payload)
        runs_ms.append((time.perf_counter() - started) * 1000.0)
        assert status == 200 and second["cache"] == "hit" and second["baselineMs"] == 0.0
        assert second["whatIf"] == first["whatIf"]
    median_ms = statistics.median(runs_ms)
    assert second["method"] == "mcub"
    assert len(second["groups"]) == 5 and all(g["model"] == "alpha" for g in second["groups"])
    group = next(g for g in second["groups"] if PERF_EVENT in g["members"])
    assert sorted(r["id"] for r in second["events"]) == sorted(group["members"])
    assert second["baseline"] == api.headline()
    assert second["whatIf"] > second["baseline"] > 0
    # The factor moves this top event by a small amount only, so "bigger than the baseline" proves
    # little: the number must be the headline of the same file with every member of the group
    # typed in at factor * q (the group stays applied, its members being identical), through the
    # existing engine.
    from fta_web import engine

    typed = json.loads(json.dumps(doc))
    stack = [typed["tree"]]
    while stack:
        node = stack.pop()
        if node.get("id") in group["members"]:
            node["probability"] = node["probability"] * FACTOR
        stack.extend(node.get("children") or [])
    hand = engine.summary(typed["tree"], typed.get("analysis"))
    assert hand["headlineMethod"] == "mcub"
    assert second["whatIf"] == close(hand["headline"], 1e-10)

    result = {
        "id": "PERF-8-alpha",
        "what": "POST /api/whatif (baseline cached) on the 301-node fixture with five alpha "
                "groups, factor %g on %s: one discarded warm-up, then %d timed calls"
                % (FACTOR, PERF_EVENT, PERF_CALLS),
        "file": "fta_web/tests/fixtures/perf_alpha_301.json",
        "medianMs": median_ms, "runsMs": runs_ms, "boundMs": PERF_BOUND_MS,
        "calls": PERF_CALLS, "warmUpBuildMs": first["baselineMs"],
        "groupsApplied": len(second["groups"]),
        "date": datetime.date.today().isoformat(),
    }
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    assert not ABSOLUTE_PATH.search(text), "an artifact must not hold an absolute path"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "PERF-8-alpha.json").write_text(text, encoding="utf-8", newline="\n")
    assert median_ms <= PERF_BOUND_MS, "PERF-8 alpha: median %.1f ms over %.0f ms (all: %s)" % (
        median_ms, PERF_BOUND_MS, ["%.1f" % t for t in runs_ms])
