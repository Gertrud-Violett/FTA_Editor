"""Shared helpers of the F4 (What-if sliders) acceptance tests.

Written from DESIGN.md of F4 (sections 2 to 4, 6 and 10), BRIEF.md and SPEC 4.5,
7.4 (R1) and 7.5, before any F4 code exists. Nothing here imports a product module
at the top of the file: the helpers that need one import it inside the function,
and ``fta_web.whatif`` is imported only by the tests that read the cache, inside
the test. So an F4 module that is not built yet fails the tests that need it and
stops nothing else from being collected.

``make_app`` builds a bare Flask app from the blueprints, imported through the
``fta_web`` package (``create_app()`` imports them by bare name and would give
them a second AppState). The what-if blueprint is added when
``fta_web.routes.whatif`` exists; until then ``POST /api/whatif`` answers 404 and
every test that calls it fails on that status and on nothing else.

The documents are built with the ``_ccf_models`` helpers of the F2 tests (loaded
by path under a private name, so this file works without the F2 conftest).
"""
import copy
import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
#: <repo>/fta_web/tests/acceptance/whatif/whatif_support.py -> parents[3] is the repo root.
REPO_ROOT = HERE.parents[3]
FIXTURES = REPO_ROOT / "fta_web" / "tests" / "fixtures"
ARTIFACTS = REPO_ROOT / ".division" / "artifacts" / "perf"

URL = "/api/whatif"

_spec = importlib.util.spec_from_file_location(
    "fta_f4_ccf_models", HERE.parent / "ccf" / "_ccf_models.py")
M = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("fta_f4_ccf_models", M)
_spec.loader.exec_module(M)

#: Sentinel: leave this key out of the request body.
OMIT = object()

# --------------------------------------------------------------------------
# tolerances
# --------------------------------------------------------------------------


def rel(expected, tol=1e-9):
    """``pytest.approx`` with exactly the stated relative tolerance.

    ``pytest.approx(x, rel=t)`` also keeps an absolute tolerance of 1e-12, which is larger
    than ``t * x`` for every expected value below 1e-3 (most of the range of these tests): the
    stated tolerance would not be the applied one. ``abs=0`` removes it.
    """
    return pytest.approx(expected, rel=tol, abs=0)


def absolute(expected, tol):
    """``pytest.approx`` with exactly the stated absolute tolerance (no relative part)."""
    return pytest.approx(expected, abs=tol, rel=0)


# --------------------------------------------------------------------------
# hand-calculated numbers shared by several files (derivations in the tests)
# --------------------------------------------------------------------------

#: R1 (SPEC 7.4): A, B fixed 1e-3 under an AND, beta group beta = 0.1, Q_t = 1e-3.
#: CCF event 0.1 * 1e-3 = 1e-4; independent part 0.9 * 1e-3 = 9e-4 each, set {A', B'} 8.1e-7.
#: MCUB = 1 - (1 - 1e-4)(1 - 8.1e-7) = 1e-4 + 8.1e-7 - 8.1e-11 = 1.00809919e-4.
R1_BASELINE = 1.00809919e-4
#: f = 10 on A (and so on B): Q_t = 1e-2; CCF event 1e-3; independent 9e-3 each, set 8.1e-5.
#: MCUB = 1 - (1 - 1e-3)(1 - 8.1e-5) = 1e-3 + 8.1e-5 - 8.1e-8 = 1.080919e-3.
R1_F10 = 1.080919e-3
#: R1_F10 / R1_BASELINE = 1.080919e-3 / 1.00809919e-4 (exact fractions, 14 digits).
R1_F10_RATIO = 10.72234766898285

#: rate, lambda = 1e-5 /h, T = 1000 h (SPEC FN-55): q = 1 - exp(-lambda T).
RATE_Q_NOMINAL = 0.009950166250831947      # 1 - exp(-0.01)
RATE_Q_F10 = 0.0951625819640404            # 1 - exp(-0.1)  (SPEC: 0.0951626)

#: models_doc: OR[RATE, STBY, REPA, FIX] = 1 - (1 - 0.009950166250831947)(1 - 5e-3)(1 - 1/101)(1 - 0.5)
MODELS_BASELINE = 0.5123269383265237
#: RATE f = 10 (q 0.0951625819640404), the others nominal.
MODELS_RATE_10 = 0.554300380719911
#: STBY f = 10 (q 0.05).
MODELS_STBY_10 = 0.5343825039298467
#: REPA f = 10 (q 1/11).
MODELS_REPA_10 = 0.5522274615543535
#: FIX f = 0.01 (q 0.005).
MODELS_FIX_001 = 0.029530607269782072

# --------------------------------------------------------------------------
# tree and document builders
# --------------------------------------------------------------------------


def rate(lam=1e-5, t=1000.0):
    return {"model": "rate", "lambda": lam, "T": t}


def standby(lam=1e-4, tau=100.0):
    return {"model": "standby", "lambda": lam, "tau": tau}


def repairable(lam=1e-3, mu=0.1):
    return {"model": "repairable", "lambda": lam, "mu": mu}


def models_tree():
    """root OR [RATE, STBY, REPA, FIX], no repeated event, no group: a tree-walk headline.

    RATE   rate, lambda 1e-5 /h, T 1000 h          q = 1 - exp(-0.01) = 0.009950166250831947
    STBY   standby, lambda 1e-4 /h, tau 100 h      q = lambda tau / 2  = 5e-3
    REPA   repairable, lambda 1e-3, mu 0.1         q = lambda / (lambda + mu) = 1/101
    FIX    fixed q = 0.5
    """
    return M.top([
        M.leaf("RATE", 0.0, name="Rate event", quant=rate()),
        M.leaf("STBY", 0.0, name="Standby event", quant=standby()),
        M.leaf("REPA", 0.0, name="Repairable event", quant=repairable()),
        M.leaf("FIX", 0.5, name="Fixed event"),
    ])


def models_doc(**kw):
    return M.document(models_tree(), None, **kw)


def standby_clamp_doc():
    """One standby event whose factor 10 pushes lambda tau / 2 above 1.

    lambda 1e-3 /h, tau 1000 h: nominal lambda tau / 2 = 0.5; f = 10: 1e-2 * 1000 / 2 = 5 > 1.
    A second event keeps the root a gate with two children.
    """
    return M.document(M.top([
        M.leaf("SBY", 0.0, name="Standby clamp", quant=standby(1e-3, 1000.0)),
        M.leaf("OTH", 1e-3, name="Other event"),
    ]), None)


def rate_group_doc():
    """root OR [ G1 AND [A, B] ], A and B rate (lambda 1e-5 /h, T 1000 h), beta group g1 (0.1)."""
    members = [M.leaf(i, 0.0, name="Pump %s" % i, quant=rate()) for i in ("A", "B")]
    tree = M.top([M.gate("G1", "AND", members, name="Pumps fail")])
    return M.document(tree, [M.group()])


def repeated_tree():
    """root AND [ G1 OR [A, B], G2 OR [X, C] ]; X (q 0) has an OR link to A, so A is reached twice.

    The cut sets are {A}, {B, X} (probability 0) and {B, C}.  A 0.01, B = C = 0.1.
    MCUB = 1 - (1 - 0.01)(1 - 0)(1 - 0.1 * 0.1) = 0.0199.
    The tree walk would give (1 - 0.99 * 0.9)^2 = 0.011881 (it counts A twice).
    """
    return M.gate("root", "AND", [
        M.gate("G1", "OR", [M.leaf("A", 0.01, name="Event A"), M.leaf("B", 0.1, name="Event B")],
               name="Branch 1"),
        M.gate("G2", "OR", [
            M.leaf("X", 0.0, name="Event X", links=[{"target_id": "A", "relation": "OR"}]),
            M.leaf("C", 0.1, name="Event C")], name="Branch 2"),
    ], name="Top event", type_="Root")


def repeated_doc():
    return M.document(repeated_tree(), None)


def unapplied_group_doc():
    """R1 shape, but B has q 2e-3: the members differ, so FN-33 does not apply the group.

    Both members are then ordinary events: AND[A, B] with the tree walk as headline.
    """
    tree = M.top([M.gate("G1", "AND", [M.pump("A", 1e-3), M.pump("B", 2e-3)], name="Pumps fail"),
                  M.leaf("C", 0.0, name="Sensor C")])
    return M.document(tree, [M.group()])


def zero_doc():
    """root OR [Z, Y], both fixed q = 0: baseline 0."""
    return M.document(M.top([M.leaf("Z", 0.0, name="Zero Z"), M.leaf("Y", 0.0, name="Zero Y")]),
                      None)


def missing_param_doc():
    """root OR [OK, BAD]: BAD is a rate event without a lambda (it cannot be evaluated)."""
    return M.document(M.top([
        M.leaf("OK", 1e-3, name="Fine event"),
        M.leaf("BAD", 1e-3, name="Broken event", quant={"model": "rate", "T": 1000.0}),
    ]), None)


def special_doc():
    """A, B under an AND, a house event H, a gate SUB and a transfer XF to it."""
    tree = M.top([
        M.gate("G1", "AND", [M.pump("A"), M.pump("B")], name="Pumps fail"),
        M.leaf("H", 1.0, name="Mode switch", eventKind="house", houseState=True),
        M.gate("SUB", "AND", [M.leaf("C"), M.leaf("D")], name="Sub tree"),
        M.leaf("XF", 1.0, name="Transfer to sub", gateType="TRANSFER", transferTo="SUB"),
    ])
    return M.document(tree, None)


def r1_doc(**kw):
    return M.r1_document(**kw)


def r1_cutoff_doc(cutoff=1e-6):
    """R1 with ``analysis.cutsets.cutoff``: the independent set (8.1e-7) is below 1e-6."""
    return M.r1_document(analysis={"cutsets": {"cutoff": cutoff}})


def r1_analysis_doc(**cutsets):
    """R1 with these ``analysis.cutsets`` settings (``maxOrder``, ``cutoff``, ...)."""
    return M.r1_document(analysis={"cutsets": dict(cutsets)})


def and_of_ors_doc():
    """root AND [ G1 OR [A, B], G2 OR [C, D] ], all fixed 0.1: no repeated event, no group.

    The headline is the tree walk. The min-cut upper bound of the same tree is a different
    number (0.11545975 at baseline-like values), so this is the document that tells the two
    methods apart (a single OR gives the same number under both).
    """
    tree = M.gate("root", "AND", [
        M.gate("G1", "OR", [M.leaf("A", 0.1, name="Event A"), M.leaf("B", 0.1, name="Event B")],
               name="Branch 1"),
        M.gate("G2", "OR", [M.leaf("C", 0.1, name="Event C"), M.leaf("D", 0.1, name="Event D")],
               name="Branch 2"),
    ], name="Top event", type_="Root")
    return M.document(tree, None)


def group_doc(q=0.5):
    """root OR [ G1 AND [A, B] ], A and B fixed ``q``, beta group g1 (0.1): R1 with another q."""
    tree = M.top([M.gate("G1", "AND", [M.pump("A", q), M.pump("B", q)], name="Pumps fail")])
    return M.document(tree, [M.group()])


def single_event_doc(quant, other=1e-3):
    """root OR [ E (``quant``), OTH (fixed ``other``) ]: one event of the model under test."""
    return M.document(M.top([
        M.leaf("E", 0.0, name="Event E", quant=quant),
        M.leaf("OTH", other, name="Other event"),
    ]), None)


def group_and_rate_doc():
    """R1 (group g1 on A, B under an AND) plus P, a rate event (1e-5 /h, 1000 h), and C (0)."""
    tree = M.top([M.gate("G1", "AND", [M.pump("A"), M.pump("B")], name="Pumps fail"),
                  M.leaf("P", 0.0, name="Rate P", quant=rate()),
                  M.leaf("C", 0.0, name="Sensor C")])
    return M.document(tree, [M.group()])


def two_groups_doc():
    """root OR [ G1 AND [A, B], G2 AND [D, E] ], all fixed 1e-3, beta groups g1 (A, B) and
    g2 "Valves" (D, E), beta 0.1 each."""
    tree = M.top([M.gate("G1", "AND", [M.pump("A"), M.pump("B")], name="Pumps fail"),
                  M.gate("G2", "AND", [M.pump("D"), M.pump("E")], name="Valves fail")])
    return M.document(tree, [M.group(), M.group("g2", "Valves", members=("D", "E"))])


def underflow_doc():
    """root AND [ A 1e-162, B 1e-162 ]: the product 1e-324 underflows to 0.0 (baseline 0);
    with A at 100 times it is 1e-322 (a denormal, above 0)."""
    return M.document(M.gate("root", "AND", [
        M.leaf("A", 1e-162, name="Tiny A"), M.leaf("B", 1e-162, name="Tiny B")],
        name="Top event", type_="Root"), None)


def overflow_doc(n=160):
    """root AND of ``n`` events, fixed 0.01: baseline 0.01 ** 160 = 1e-320 (a denormal); with
    every factor 100 each q is 1 and the top event 1.0, so the quotient overflows to infinity."""
    return M.document(M.gate("root", "AND", [
        M.leaf("E%d" % i, 0.01, name="Event %d" % i) for i in range(n)],
        name="Top event", type_="Root"), None)


def small_group_doc(q=1e-12, cutoff=1e-30):
    """R1 shape with tiny q and a tiny cutoff, so that nothing is dropped: CCF event 1e-13, the
    independent set (9e-13) ** 2 = 8.1e-25."""
    tree = M.top([M.gate("G1", "AND", [M.pump("A", q), M.pump("B", q)], name="Pumps fail")])
    return M.document(tree, [M.group()], analysis={"cutsets": {"cutoff": cutoff}})


def walk(node):
    yield node
    for child in node.get("children") or []:
        yield from walk(child)


def hand_headline(doc, ids, q):
    """``engine.summary`` (the existing engine) of ``doc`` with the events ``ids`` typed in as
    fixed probability ``q``: what a user who edits those events by hand sees as the headline."""
    from fta_web import engine

    tree = copy.deepcopy(doc["tree"])
    for node in walk(tree):
        if node.get("id") in ids:
            node["quant"] = {"model": "fixed"}
            node["probability"] = q
    return engine.summary(tree, doc.get("analysis"))


# --------------------------------------------------------------------------
# the app and the client
# --------------------------------------------------------------------------


def make_app(root):
    """A bare Flask app with every blueprint that exists; see the module docstring."""
    import flask

    from fta_web import errors
    from fta_web.routes.ai import ai_bp
    from fta_web.routes.analysis import analysis_bp
    from fta_web.routes.ccf import ccf_bp
    from fta_web.routes.files import files_bp
    from fta_web.routes.fmea import fmea_bp
    from fta_web.routes.grid import grid_bp
    from fta_web.routes.render import render_bp
    from fta_web.routes.report import report_bp
    from fta_web.routes.tree import tree_bp
    from fta_web.routes.validate import validate_bp
    from fta_web.state import get_state, reset_state

    reset_state()
    app = flask.Flask(__name__)

    @app.errorhandler(errors.ApiError)
    def _handle(err):  # the real app registers the same handler
        return errors.api_error_response(err)

    blueprints = [tree_bp, files_bp, render_bp, analysis_bp, validate_bp, report_bp, fmea_bp,
                  ai_bp, ccf_bp, grid_bp]
    try:
        from fta_web.routes.whatif import whatif_bp
    except ModuleNotFoundError as exc:
        # Only "the what-if route is not there yet" is tolerated: the URL then
        # answers 404. Any other import error is a real failure.
        if exc.name != "fta_web.routes.whatif":
            raise
    else:
        blueprints.append(whatif_bp)
    for blueprint in blueprints:
        app.register_blueprint(blueprint)
    app.config.update(TESTING=True)
    get_state().fs_root = Path(root)
    return app


def _refuse_constant(token):
    """A response is read as strict JSON, as the browser's ``JSON.parse`` reads it: the tokens
    NaN, Infinity and -Infinity (which Python's json would accept) are a failure, not a number.
    It raises AssertionError, which ``Api.call`` does not catch."""
    raise AssertionError("the response holds %s, which JSON does not allow (JSON.parse fails)" % token)


class Api:
    """The Flask test client with JSON in and out, and the what-if calls."""

    def __init__(self, client, root):
        self.client = client
        self.root = Path(root)

    # -- plumbing ---------------------------------------------------------

    def call(self, method, url, **kwargs):
        response = self.client.open(url, method=method, **kwargs)
        raw = response.get_data()
        try:
            body = json.loads(raw.decode("utf-8"), parse_constant=_refuse_constant)
        except (ValueError, UnicodeDecodeError):
            body = None
        return response.status_code, body

    def get(self, url, **kwargs):
        return self.call("GET", url, **kwargs)

    def post(self, url, payload=None, **kwargs):
        if payload is not None:
            kwargs["json"] = payload
        return self.call("POST", url, **kwargs)

    def patch(self, url, payload=None, **kwargs):
        if payload is not None:
            kwargs["json"] = payload
        return self.call("PATCH", url, **kwargs)

    def raw(self, method, url, text):
        """A request whose body is the exact text ``text`` (NaN, -0, 1e999 ...)."""
        return self.call(method, url, data=text.encode("utf-8"), content_type="application/json")

    def binary(self, method, url, **kwargs):
        response = self.client.open(url, method=method, **kwargs)
        return response.status_code, response.get_data()

    def open_doc(self, doc, name="doc.json"):
        """Write ``doc`` into the sandbox root and open it; the open response."""
        path = self.root / name
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        status, body = self.post("/api/file/open", {"path": str(path), "force": True})
        assert status == 200, body
        return body

    # -- the document -----------------------------------------------------

    def fields(self):
        """``{revision, documentSerial}`` as the What-if tab would send them."""
        status, body = self.get("/api/revision")
        assert status == 200, body
        return {"revision": body["revision"], "documentSerial": body["documentSerial"]}

    def headline(self):
        """The baseline: the headline float ``/api/analysis/summary`` returns."""
        status, body = self.get("/api/analysis/summary")
        assert status == 200, body
        return body["headline"]

    def summary(self):
        status, body = self.get("/api/analysis/summary")
        assert status == 200, body
        return body

    def edit(self, node_id="A", **fields):
        """A Details edit (``PATCH /api/nodes/<id>``); the mutation payload."""
        fields = fields or {"name": "Edited name"}
        status, body = self.patch("/api/nodes/%s" % node_id, fields)
        assert status == 200, body
        return body

    # -- the what-if endpoint ---------------------------------------------

    def payload(self, factors, **override):
        body = dict(self.fields(), factors=factors)
        for key, value in override.items():
            if value is OMIT:
                body.pop(key, None)
            else:
                body[key] = value
        return body

    def whatif(self, factors, **override):
        """``POST /api/whatif`` with the current revision fields; ``(status, body)``."""
        return self.post(URL, self.payload(factors, **override))

    def whatif_ok(self, factors, **override):
        status, body = self.whatif(factors, **override)
        assert status == 200, (status, body)
        assert body["ok"] is True, body
        return body

    def whatif_raw(self, text):
        return self.raw("POST", URL, text)

    def raw_with(self, factors_text, **fields):
        """The request body as text, with ``factors`` written as ``factors_text``
        (a JSON object text) and the current revision fields."""
        body = dict(self.fields(), **fields)
        parts = ['"%s": %s' % (k, json.dumps(v)) for k, v in body.items()]
        parts.append('"factors": %s' % factors_text)
        return self.raw("POST", URL, "{%s}" % ", ".join(parts))


# --------------------------------------------------------------------------
# readers and checks
# --------------------------------------------------------------------------


def error_of(body):
    assert isinstance(body, dict), "no JSON body (is the route missing?)"
    assert body["ok"] is False, body
    return body["error"]


def assert_error(result, status, code, field=None, **detail):
    """``result`` is ``(status, body)``; the envelope of errors.py, the code, the
    field and any ``detail`` key given."""
    got_status, body = result
    assert got_status == status, (got_status, body)
    err = error_of(body)
    assert err["code"] == code, err
    assert isinstance(err["message"], str) and err["message"]
    if field is not None:
        assert err["detail"]["field"] == field, err
    for key, value in detail.items():
        assert err["detail"][key] == value, err
    return err


def row_of(body, node_id):
    rows = [r for r in body["events"] if r["id"] == node_id]
    assert len(rows) == 1, (node_id, [r["id"] for r in body["events"]])
    return rows[0]


def fingerprint():
    """Everything the endpoint must leave alone (DESIGN 2.3), comparable with ``==``."""
    from fta_web.state import get_state

    state = get_state()
    with state.lock:
        return {
            "revision": state.revision,
            "documentSerial": state.document_serial,
            "canUndo": state.can_undo,
            "canRedo": state.can_redo,
            "dirty": state.dirty,
            "currentPath": str(state.current_path) if state.current_path else None,
            "undoDepth": len(state._undo),
            "redoDepth": len(state._redo),
            "snapshot": state.snapshot(),
        }


def whatif_module():
    """``fta_web.whatif``; raises ModuleNotFoundError (a failing test) until F4 exists."""
    return importlib.import_module("fta_web.whatif")


def whatif_module_if_built():
    """``fta_web.whatif`` or None. Only for fixtures that tidy up: a test never uses it."""
    try:
        return importlib.import_module("fta_web.whatif")
    except ModuleNotFoundError as exc:
        if exc.name != "fta_web.whatif":
            raise
        return None


def load_perf_fixture():
    return json.loads((FIXTURES / "perf_ccf_301.json").read_text(encoding="utf-8"))


def deep(value):
    return copy.deepcopy(value)
