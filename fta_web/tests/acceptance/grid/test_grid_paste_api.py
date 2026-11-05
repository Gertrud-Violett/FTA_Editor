"""F3 acceptance tests (T0): ``POST /api/grid/paste``, server side.

Written from SPEC 4.4 / 4.7 / 7.5 and DESIGN.md section 5.3 and 5.4, before any
F3 code exists. Until ``fta_web/routes/grid.py`` exists the URL answers 404 and
each test fails on that status; nothing here imports an F3 module at import time
(``grid_schema`` is imported inside the tests that need it).

CRITERION -> TEST MAP (BRIEF .division/features/F3/BRIEF.md)
============================================================
 1  UI-9   Grid tab, headers, q read-only ..... GUI s_grid.js  (criterion1_*)
 2  UI-10  sort and filter ..................... GUI s_grid.js  (criterion2_*)
 3  UI-12  summary after a paste ............... GUI s_grid.js  (criterion3_*)
 4  FN-46  one meaning per field
          * vector file ..................... test_grid_numbers.py (file shape, FN-46 tables, >= 30 inputs)
          * beta / alpha_k, and every column,
            against the real parsers under Node  test_grid_numbers.py
          * server ranges against the vectors .. test_grid_numbers.py
          * q/lambda/T/tau/mu typed in the field, typed in the cell,
            pasted: for every input ............. GUI s_grid.js  (criterion4_*)
          * grid.js imports the parsers, defines
            none ............................... test_grid_source.py
 5  FN-47  paste addressing, 409, one undo step
          * stale revision / documentSerial: 409,
            nothing applied, no undo step ...... this file (test_stale_*, test_409_*)
          * one undo restores a whole multi-row
            paste; no-op paste pushes no step .. this file (test_one_undo_step_*, test_noop_*)
          * sort + filter + 3 x 3 block on the
            intended ids; stale message in the
            browser; Ctrl+Z after 50 rows ...... GUI s_grid.js  (criterion5_*)
 6  FN-50  the ten rows of the table. Who decides (DESIGN 5.4):
          * empty cell, filtered row, trailing newline, Excel quoting, extra cells,
            extra rows, more than 2,000 rows (browser side: no request),
            q pre-dropped when equal after rounding ... GUI s_grid.js (criterion6_*)
          * id column (equal ignored / different refuses) ... this file (test_fn50_id_*)
          * q on a non-fixed model (equal ignored / different refuses) ... this file (test_fn50_q_*)
          * any invalid cell refuses the whole row, valid rows apply ... this file (test_fn50_invalid_cell_*)
          * more than 2,000 rows: the server also answers 400 ... this file (test_fn50_rows_cap_*)
          * an empty cell is never sent (omitted): the server's view of it ... this file (test_fn50_empty_cell_*)
 7  FN-51  units: the server stores what it receives (this file, test_fn51_*);
          1 FIT -> 1e-9 /h and 8.76 /y -> 1e-3 /h by the Quantification tab's own
          factors, run under Node ... this file (test_fn51_unit_factors_*);
          the header unit picker in the browser ... GUI s_grid.js (criterion7_*)
 8  FN-70  per field: number, "0.1", NaN, Infinity, -0.1, 1.5 for q; revision and
          documentSerial; -0 stored as 0; body not an object; unknown cell key;
          duplicate nodeId; more than 2,000 rows; ETA mode; existing routes unchanged
          ... this file (test_fn70_*, test_existing_routes_*); direct validators
          ... test_grid_numbers.py (test_validator_*)
 9  PERF-6 ... GUI s_grid.js (criterion9_perf6) -> PERF-6.json
10  PERF-7 ... GUI s_grid.js (criterion10_perf7) -> PERF-7.json
11  UI-18 / FN-64 texts ... not part of T0 (text review; test_catalog_parity.py and
    test_i18n.py cover the catalogs once they exist)

Open points of DESIGN.md taken as binding here: 5 (NOT_USED refuses the row),
7 (out-of-range / non-number cells answer 400 for the whole request), 8 (a row
that only repeats id / q is neither applied nor refused; a row that writes the
stored value is applied but costs no undo step).
"""
import importlib.util
import json
import math
from pathlib import Path

import pytest

_SUPPORT = Path(__file__).with_name("grid_support.py")
_spec = importlib.util.spec_from_file_location("fta_f3_grid_support", _SUPPORT)
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

STALE_MESSAGE = "The analysis changed; paste again"
SYMBOL = {"lambda": "λ", "T": "T", "tau": "τ", "mu": "μ"}


@pytest.fixture
def client(tmp_path):
    app = S.make_app(tmp_path)
    with app.test_client() as test_client:
        yield test_client
    from fta_web.state import reset_state

    reset_state()


@pytest.fixture
def doc(client):
    """The small document: ids by role (fixed, rate, standby, repairable, ...)."""
    return S.build_document(client)


def snapshot():
    """Everything a paste can change, per node, comparable with ``==``."""
    out = {}

    def walk(node):
        out[str(node["id"])] = json.dumps(
            {k: node.get(k) for k in ("name", "probability", "quant", "trace")}, sort_keys=True)
        for child in node.get("children") or []:
            walk(child)

    walk(S.state().core.get_data())
    return out


def assert_nothing_changed(before, depth, revision=None, client=None):
    assert snapshot() == before
    assert S.undo_depth() == depth
    if revision is not None:
        assert S.fields_now(client)["revision"] == revision


# ---------------------------------------------------------------------------
# the endpoint exists and answers as DESIGN 5.3 says
# ---------------------------------------------------------------------------


def test_the_grid_blueprint_is_registered_in_the_real_app():
    from fta_web.app import create_app

    rules = {rule.rule for rule in create_app().url_map.iter_rules()}
    assert S.PASTE_URL in rules


def test_the_stale_revision_error_code_is_a_shared_constant():
    from fta_web import errors

    assert errors.STALE_REVISION == "STALE_REVISION"


def test_a_paste_answers_with_applied_refused_and_the_mutation_payload(client, doc):
    before = S.fields_now(client)
    response = S.paste(client, [S.row(1, doc["rate"], **{"lambda": 2e-4, "T": 200.0, "source": "vendor data"})])
    payload = S.assert_ok(response)
    assert payload["applied"] == 1
    assert payload["refused"] == []
    for key in ("tree", "zeroNodes", "dirty", "canUndo", "canRedo", "analysis",
                "sessionWarnings", "revision", "documentSerial"):
        assert key in payload, key
    assert payload["dirty"] is True and payload["canUndo"] is True and payload["canRedo"] is False
    assert payload["revision"] == before["revision"] + 1
    assert payload["documentSerial"] == before["documentSerial"]
    quant = S.quant_of(doc["rate"])
    assert quant["lambda"] == 2e-4 and quant["T"] == 200.0 and quant["source"] == "vendor data"
    assert quant["model"] == "rate"


def test_a_paste_recalculates_like_the_node_update_route(client, doc):
    twin = S.add(client, name="Twin", probability=0.5, quant={"model": "rate", "lambda": 1e-4, "T": 100})
    S.assert_ok(S.paste(client, [S.row(1, doc["rate"], **{"lambda": 3e-4, "T": 40.0})]))
    patched = client.patch("/api/nodes/" + twin, json={"quant": {"lambda": 3e-4, "T": 40.0}})
    assert patched.status_code == 200
    assert S.stored(doc["rate"])["probability"] == S.stored(twin)["probability"]
    assert S.stored(doc["rate"])["probability"] != 0.5


def test_every_column_of_a_row_is_written(client, doc):
    cells = {"name": "  Renamed \t pump ", "model": "standby", "lambda": 5e-5, "tau": 72.0,
             "source": "line one\nline two\tcol", "tags": "a; b ;; c ;"}
    payload = S.assert_ok(S.paste(client, [S.row(1, doc["rate"], **cells)]))
    assert payload["applied"] == 1 and payload["refused"] == []
    node = S.stored(doc["rate"])
    assert node["name"] == "Renamed pump"  # DESIGN open point 4: same sanitiser as a typed name
    assert node["quant"]["model"] == "standby"
    assert node["quant"]["lambda"] == 5e-5 and node["quant"]["tau"] == 72.0
    assert node["quant"]["source"] == "line one\nline two\tcol"  # text kept as pasted
    assert node["trace"]["tags"] == ["a", "b", "c"]


def test_tags_are_split_on_semicolons_and_the_full_width_separators(client, doc):
    """DESIGN 5.3 rule 6: the same separators as a typed tag cell (; and the full-width ; and the ideographic comma)."""
    cells = {"tags": "a; b；c、 d ;; ;e"}
    payload = S.assert_ok(S.paste(client, [S.row(1, doc["fixed"], **cells)]))
    assert payload["applied"] == 1 and payload["refused"] == []
    assert S.stored(doc["fixed"])["trace"]["tags"] == ["a", "b", "c", "d", "e"]


def test_q_on_a_fixed_row_sets_the_probability(client, doc):
    payload = S.assert_ok(S.paste(client, [S.row(1, doc["fixed"], q=0.375)]))
    assert payload["applied"] == 1
    assert S.stored(doc["fixed"])["probability"] == 0.375


def test_the_model_cell_is_applied_before_the_other_cells_of_its_row(client, doc):
    payload = S.assert_ok(S.paste(client, [
        S.row(1, doc["fixed"], model="rate", **{"lambda": 1e-5, "T": 1000.0}),
        S.row(2, doc["rate"], model="fixed", q=0.3),
    ]))
    assert payload["applied"] == 2 and payload["refused"] == []
    assert S.quant_of(doc["fixed"]) == {"model": "rate", "lambda": 1e-5, "T": 1000.0}
    assert S.stored(doc["rate"])["probability"] == 0.3
    assert S.quant_of(doc["rate"])["model"] == "fixed"


def test_events_below_a_gate_are_rows_and_a_paste_may_name_them(client, doc):
    payload = S.assert_ok(S.paste(client, [S.row(1, doc["nested"], q=0.4)]))
    assert payload["applied"] == 1
    assert S.stored(doc["nested"])["probability"] == 0.4


# ---------------------------------------------------------------------------
# criterion 5: revision / documentSerial, 409, one undo step
# ---------------------------------------------------------------------------


def test_stale_revision_answers_409_and_applies_nothing(client, doc):
    old = S.fields_now(client)
    assert client.patch("/api/nodes/" + doc["fixed2"], json={"name": "Changed elsewhere"}).status_code == 200
    now = S.fields_now(client)
    assert now["revision"] > old["revision"]
    before, depth = snapshot(), S.undo_depth()
    response = S.paste(client, [S.row(1, doc["rate"], **{"lambda": 9e-4}), S.row(2, doc["fixed"], q=0.9)],
                       revision=old["revision"])
    error = S.assert_error(response, 409, "STALE_REVISION")
    assert error["message"] == STALE_MESSAGE
    assert error["detail"] == {"revision": now["revision"], "documentSerial": now["documentSerial"]}
    assert_nothing_changed(before, depth, now["revision"], client)
    again = S.paste(client, [S.row(1, doc["rate"], **{"lambda": 9e-4})])  # drawn again: accepted
    assert S.assert_ok(again)["applied"] == 1


def test_a_revision_from_the_future_is_stale_too(client, doc):
    now = S.fields_now(client)
    before, depth = snapshot(), S.undo_depth()
    S.assert_error(S.paste(client, [S.row(1, doc["fixed"], q=0.9)], revision=now["revision"] + 1),
                   409, "STALE_REVISION")
    assert_nothing_changed(before, depth, now["revision"], client)


def test_stale_document_serial_answers_409_and_applies_nothing(client, doc):
    old = S.fields_now(client)
    assert client.post("/api/new", json={"force": True}).status_code == 200
    fresh = S.build_document(client)
    now = S.fields_now(client)
    assert now["documentSerial"] != old["documentSerial"]
    before, depth = snapshot(), S.undo_depth()
    # the revision is the current one; only the document serial is old
    response = S.paste(client, [S.row(1, fresh["fixed"], q=0.9)], serial=old["documentSerial"])
    error = S.assert_error(response, 409, "STALE_REVISION")
    assert error["message"] == STALE_MESSAGE
    assert error["detail"] == {"revision": now["revision"], "documentSerial": now["documentSerial"]}
    assert_nothing_changed(before, depth, now["revision"], client)


def test_409_body_is_the_error_envelope(client, doc):
    now = S.fields_now(client)
    response = S.paste(client, [S.row(1, doc["fixed"], q=0.9)], revision=now["revision"] + 5)
    payload = S.body(response)
    assert set(payload) == {"ok", "error"} and payload["ok"] is False
    assert set(payload["error"]) == {"code", "message", "detail"}


def test_a_request_that_is_invalid_and_stale_is_a_400_not_a_409(client, doc):
    """DESIGN 5.3 order: read and validate everything (400), then ETA, then stale (409)."""
    now = S.fields_now(client)
    response = S.paste(client, [S.row(1, doc["fixed"], q=1.5)], revision=now["revision"] + 1)
    S.assert_error(response, 400, "INVALID_FIELD", "q")


def test_one_undo_step_for_a_whole_multi_row_paste(client, doc):
    before, depth = snapshot(), S.undo_depth()
    rows = [
        S.row(1, doc["rate"], **{"lambda": 7e-5, "T": 12.0}),
        S.row(2, doc["standby"], tau=33.0, source="s2"),
        S.row(3, doc["repairable"], mu=2.5, name="Delta renamed"),
        S.row(4, doc["fixed"], q=0.45, tags="x; y"),
        S.row(5, doc["fixed2"], q=0.55),
    ]
    payload = S.assert_ok(S.paste(client, rows))
    assert payload["applied"] == 5 and payload["refused"] == []
    assert snapshot() != before
    assert S.undo_depth() == depth + 1, "a paste of five rows must be one undo step"
    undone = client.post("/api/undo")
    assert undone.status_code == 200, S.body(undone)
    assert snapshot() == before, "one undo must restore every row of the paste"
    assert S.undo_depth() == depth


def test_one_undo_step_when_some_rows_are_refused(client, doc):
    depth = S.undo_depth()
    payload = S.assert_ok(S.paste(client, [
        S.row(1, doc["fixed"], q=0.45),
        S.row(2, doc["rate"], tau=5.0),  # not used by a rate model: refused
        S.row(3, doc["fixed2"], q=0.55),
    ]))
    assert payload["applied"] == 2 and len(payload["refused"]) == 1
    assert S.undo_depth() == depth + 1


def test_a_paste_clears_the_redo_history_like_any_edit(client, doc):
    assert client.post("/api/undo").status_code == 200
    assert S.body(client.get("/api/revision"))  # the document is still there
    payload = S.assert_ok(S.paste(client, [S.row(1, doc["fixed"], q=0.45)]))
    assert payload["canRedo"] is False and payload["canUndo"] is True


def test_noop_paste_pushes_no_undo_step_and_keeps_the_redo_history(client, doc):
    assert client.patch("/api/nodes/" + doc["fixed2"], json={"name": "Renamed"}).status_code == 200
    assert client.post("/api/undo").status_code == 200  # one step on the redo stack
    S.state().mark_saved()
    before, depth = snapshot(), S.undo_depth()
    revision = S.fields_now(client)["revision"]
    stored_lambda = S.quant_of(doc["rate"])["lambda"]
    payload = S.assert_ok(S.paste(client, [S.row(1, doc["rate"], **{"lambda": stored_lambda}),
                                           S.row(2, doc["fixed"], q=0.1)]))
    assert payload["applied"] == 2 and payload["refused"] == []  # DESIGN open point 8
    assert payload["canRedo"] is True
    assert payload["dirty"] is False
    assert payload["revision"] == revision
    assert_nothing_changed(before, depth, revision, client)


def test_a_paste_with_no_rows_is_a_noop(client, doc):
    before, depth = snapshot(), S.undo_depth()
    payload = S.assert_ok(S.paste(client, []))
    assert payload["applied"] == 0 and payload["refused"] == []
    assert_nothing_changed(before, depth)


def test_a_paste_of_refused_rows_only_is_a_noop(client, doc):
    before, depth = snapshot(), S.undo_depth()
    revision = S.fields_now(client)["revision"]
    payload = S.assert_ok(S.paste(client, [S.row(1, doc["rate"], tau=5.0), S.row(2, doc["gate"], q=0.5)]))
    assert payload["applied"] == 0 and len(payload["refused"]) == 2
    assert_nothing_changed(before, depth, revision, client)


# ---------------------------------------------------------------------------
# criterion 6: the FN-50 rows the server decides
# ---------------------------------------------------------------------------


def test_fn50_id_equal_to_the_row_is_ignored(client, doc):
    payload = S.assert_ok(S.paste(client, [
        S.row(1, doc["rate"], id=doc["rate"], **{"lambda": 6e-5}),
        S.row(2, doc["fixed"], id="  %s  " % doc["fixed"], q=0.6),
    ]))
    assert payload["applied"] == 2 and payload["refused"] == []
    assert S.quant_of(doc["rate"])["lambda"] == 6e-5
    assert S.stored(doc["fixed"])["probability"] == 0.6


def test_fn50_a_row_holding_only_the_equal_id_is_neither_applied_nor_refused(client, doc):
    before, depth = snapshot(), S.undo_depth()
    payload = S.assert_ok(S.paste(client, [S.row(1, doc["rate"], id=doc["rate"])]))
    assert payload["applied"] == 0 and payload["refused"] == []
    assert_nothing_changed(before, depth)


def test_fn50_id_different_refuses_the_row(client, doc):
    before = snapshot()
    payload = S.assert_ok(S.paste(client, [
        S.row(3, doc["rate"], id=doc["fixed"], **{"lambda": 6e-5, "source": "must not land"}),
    ]))
    assert payload["applied"] == 0
    assert payload["refused"] == [
        {"clipRow": 3, "column": "id", "code": "ID_MISMATCH", "message": "id does not match this row"}]
    assert snapshot() == before, "a refused row changes nothing, not even its valid cells"


def test_fn50_q_on_a_non_fixed_model_equal_to_the_shown_q_is_ignored(client, doc):
    shown = S.stored(doc["rate"])["probability"]
    payload = S.assert_ok(S.paste(client, [
        S.row(1, doc["rate"], q=shown, **{"lambda": 2e-4}),
        S.row(2, doc["standby"], q=S.stored(doc["standby"])["probability"] * (1 + 1e-10)),
    ]))
    assert payload["applied"] == 1 and payload["refused"] == []  # row 2 only repeated q
    assert S.quant_of(doc["rate"])["lambda"] == 2e-4


def test_fn50_q_zero_equals_a_zero_computed_q(client, doc):
    assert client.patch("/api/nodes/" + doc["rate"], json={"quant": {"lambda": 0}}).status_code == 200
    assert S.stored(doc["rate"])["probability"] == 0
    before, depth = snapshot(), S.undo_depth()
    payload = S.assert_ok(S.paste(client, [S.row(1, doc["rate"], q=0)]))
    assert payload["applied"] == 0 and payload["refused"] == []
    assert_nothing_changed(before, depth)


def test_fn50_q_on_a_non_fixed_model_that_differs_refuses_the_row(client, doc):
    before = snapshot()
    payload = S.assert_ok(S.paste(client, [S.row(5, doc["rate"], q=0.9, **{"lambda": 2e-4})]))
    assert payload["applied"] == 0
    assert payload["refused"] == [
        {"clipRow": 5, "column": "q", "code": "Q_COMPUTED", "message": "q is computed from the model"}]
    assert snapshot() == before


@pytest.mark.parametrize("role", ["rate", "standby", "repairable"])
def test_fn50_q_is_refused_on_every_non_fixed_model(client, doc, role):
    payload = S.assert_ok(S.paste(client, [S.row(1, doc[role], q=0.99999)]))
    assert S.refusals(payload) == {(1, "q"): "Q_COMPUTED"}


def test_fn50_empty_cell_is_never_sent_so_a_row_may_carry_fewer_cells(client, doc):
    """An empty cell is omitted by the browser: a row with only some cells changes only those."""
    S.assert_ok(S.paste(client, [S.row(1, doc["rate"], **{"lambda": 2e-4})]))
    assert S.quant_of(doc["rate"])["T"] == 100.0  # T was not in the row: unchanged
    assert S.stored(doc["rate"])["name"] == "Bravo rate"


def test_fn50_invalid_cell_refuses_the_whole_row_and_valid_rows_apply(client, doc):
    before = snapshot()
    rows = [
        S.row(1, doc["fixed"], q=0.45, name="Alpha ok"),
        S.row(2, doc["rate"], **{"lambda": 3e-4, "T": 10.0, "tau": 5.0, "source": "never"}),  # tau unused
        S.row(3, doc["fixed2"], q=0.55),
        S.row(4, doc["standby"], **{"lambda": 4e-4}),
    ]
    payload = S.assert_ok(S.paste(client, rows))
    assert payload["applied"] == 3
    assert payload["refused"] == [{
        "clipRow": 2, "column": "tau", "code": "NOT_USED",
        "message": "τ is not used by the model of this row"}]
    after = snapshot()
    assert after[doc["rate"]] == before[doc["rate"]], "the refused row changed nothing"
    assert S.stored(doc["fixed"])["probability"] == 0.45 and S.stored(doc["fixed"])["name"] == "Alpha ok"
    assert S.stored(doc["fixed2"])["probability"] == 0.55
    assert S.quant_of(doc["standby"])["lambda"] == 4e-4


def test_fn50_every_offending_cell_of_a_refused_row_is_reported(client, doc):
    payload = S.assert_ok(S.paste(client, [
        S.row(7, doc["rate"], id=doc["fixed"], q=0.9, tau=5.0, mu=1.0, source="x"),
    ]))
    assert payload["applied"] == 0
    assert S.refusals(payload) == {(7, "id"): "ID_MISMATCH", (7, "q"): "Q_COMPUTED",
                                   (7, "tau"): "NOT_USED", (7, "mu"): "NOT_USED"}
    for item in payload["refused"]:
        assert set(item) == {"clipRow", "column", "code", "message"}
        assert isinstance(item["message"], str) and item["message"]


@pytest.mark.parametrize("role, key", [
    ("fixed", "lambda"), ("fixed", "T"), ("fixed", "tau"), ("fixed", "mu"),
    ("rate", "tau"), ("rate", "mu"),
    ("standby", "T"), ("standby", "mu"),
    ("repairable", "T"), ("repairable", "tau"),
])
def test_fn50_a_value_for_a_field_the_model_does_not_use_refuses_the_row(client, doc, role, key):
    before = snapshot()
    payload = S.assert_ok(S.paste(client, [S.row(1, doc[role], **{key: 5.0})]))
    assert payload["applied"] == 0
    assert payload["refused"] == [{
        "clipRow": 1, "column": key, "code": "NOT_USED",
        "message": "%s is not used by the model of this row" % SYMBOL[key]}]
    assert snapshot() == before


@pytest.mark.parametrize("role, cells", [
    ("rate", {"lambda": 1e-5, "T": 5.0}),
    ("standby", {"lambda": 1e-5, "tau": 5.0}),
    ("repairable", {"lambda": 1e-5, "mu": 5.0}),
])
def test_the_fields_a_model_uses_are_accepted(client, doc, role, cells):
    payload = S.assert_ok(S.paste(client, [S.row(1, doc[role], **cells)]))
    assert payload["applied"] == 1 and payload["refused"] == []
    for key, value in cells.items():
        assert S.quant_of(doc[role])[key] == value


@pytest.mark.parametrize("target", ["gate", "unknown", "root", "house"])
def test_a_row_that_is_not_a_basic_event_is_refused(client, doc, target):
    node_id = {"gate": doc["gate"], "unknown": "no_such_node", "root": "root", "house": doc["house"]}[target]
    before = snapshot()
    payload = S.assert_ok(S.paste(client, [S.row(4, node_id, q=0.5)]))
    assert payload["applied"] == 0
    assert payload["refused"] == [{
        "clipRow": 4, "column": "", "code": "NOT_BASIC_EVENT", "message": "This row is not a basic event"}]
    assert snapshot() == before


@pytest.mark.parametrize("column, cells", [
    ("name", {"name": "bad \ud83d name"}),                 # unpaired surrogate
    ("source", {"source": "x" * 4001}),                      # longer than the text limit
    ("tags", {"tags": "; ".join("t%d" % i for i in range(70))}),  # more than 64 tags
])
def test_text_that_cannot_be_saved_refuses_the_row(client, doc, column, cells):
    before = snapshot()
    payload = S.assert_ok(S.paste(client, [S.row(2, doc["fixed"], **cells)]))
    assert payload["applied"] == 0
    assert S.refusals(payload) == {(2, column): "INVALID_TEXT"}
    assert snapshot() == before


def test_fn50_rows_cap_2000_rows_are_accepted(client, doc):
    rows = [S.row(i + 1, "missing_%d" % i, q=0.5) for i in range(2000)]
    payload = S.assert_ok(S.paste(client, rows))
    assert payload["applied"] == 0 and len(payload["refused"]) == 2000
    assert {item["code"] for item in payload["refused"]} == {"NOT_BASIC_EVENT"}


def test_fn50_rows_cap_more_than_2000_rows_is_refused_whole(client, doc):
    before, depth = snapshot(), S.undo_depth()
    rows = [S.row(1, doc["fixed"], q=0.9)] + [S.row(i + 2, "missing_%d" % i, q=0.5) for i in range(2000)]
    assert len(rows) == 2001
    S.assert_error(S.paste(client, rows), 400, "INVALID_FIELD", "rows")
    assert_nothing_changed(before, depth)


# ---------------------------------------------------------------------------
# criterion 7: units. The server stores what it receives; the browser divides.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [1e-9, 1e-3, 2e-6, 1e-12, 0.1, 3.5e-5, 1.0])
def test_fn51_lambda_is_stored_per_hour_exactly_as_received(client, doc, value):
    S.assert_ok(S.paste(client, [S.row(1, doc["rate"], **{"lambda": value})]))
    assert S.quant_of(doc["rate"])["lambda"] == value


@pytest.mark.parametrize("key, role, value", [("T", "rate", 8760.0), ("tau", "standby", 24.5), ("mu", "repairable", 0.125)])
def test_fn51_hours_and_per_hour_values_are_stored_as_received(client, doc, key, role, value):
    S.assert_ok(S.paste(client, [S.row(1, doc[role], **{key: value})]))
    assert S.quant_of(doc[role])[key] == value


def _node_run(script):
    """Run a Node ES-module script given on stdin; its stdout is JSON."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    proc = subprocess.run([node, "--input-type=module"], input=script.encode("utf-8"),
                          capture_output=True, timeout=120)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return json.loads(proc.stdout.decode("utf-8"))


def _vectors():
    path = S.FIXTURES / "number_inputs.json"
    assert path.is_file(), "missing %s" % path
    return json.loads(path.read_text(encoding="utf-8"))


def _function_source(source, name):
    """The text of ``function <name>(...) {...}`` in a JS source (brace matching)."""
    import re

    start = re.search(r"(?:export )?function %s\(" % re.escape(name), source)
    assert start, "function %s not found" % name
    depth, i = 0, source.index("{", source.index(")", start.start()))
    for j in range(i, len(source)):
        depth += source[j] == "{"
        depth -= source[j] == "}"
        if depth == 0:
            return source[start.start():j + 1].replace("export ", "", 1)
    raise AssertionError("unbalanced braces in %s" % name)


def test_fn51_unit_factors_of_the_quantification_tab_give_the_spec_values(client, doc):
    """1 FIT -> 1e-9 /h and 8.76 /y -> 1e-3 /h, with the Quantification tab's own
    LAMBDA_UNITS and parseNumber (their source text, run under Node), then stored by the server."""
    import re

    js = Path(__file__).resolve().parents[3] / "static" / "js" / "tabs"
    quant = (js / "quant.js").read_text(encoding="utf-8")
    common = (js / "analysis_common.js").read_text(encoding="utf-8")
    units = re.search(r"const LAMBDA_UNITS = (\{[^}]*\});", quant)
    assert units, "LAMBDA_UNITS not found in quant.js"
    examples = _vectors()["lambda_unit_examples"]
    script = (
        "const input = %s; const LAMBDA_UNITS = %s; %s;\n"
        "const out = input.map(e => parseNumber(e.text) / LAMBDA_UNITS[e.unit]);\n"
        "process.stdout.write(JSON.stringify(out));\n"
        % (json.dumps(examples), units.group(1), _function_source(common, "parseNumber")))
    per_hour = _node_run(script)
    for example, got in zip(examples, per_hour):
        assert got == pytest.approx(example["perHour"], rel=1e-12), (example, got)
    # the two cases of the specification, by name
    by_text = {(e["text"], e["unit"]): g for e, g in zip(examples, per_hour)}
    assert by_text[("1", "FIT")] == 1e-9
    assert by_text[("8.76", "y")] == pytest.approx(1e-3, rel=1e-12)
    # and the server keeps those numbers: 1 FIT is stored as 1e-9 /h, 8.76 /y as 1e-3 /h
    payload = S.assert_ok(S.paste(client, [S.row(1, doc["rate"], **{"lambda": by_text[("1", "FIT")]}),
                                           S.row(2, doc["standby"], **{"lambda": by_text[("8.76", "y")]})]))
    assert payload["applied"] == 2
    assert S.quant_of(doc["rate"])["lambda"] == 1e-9
    assert S.quant_of(doc["standby"])["lambda"] == pytest.approx(1e-3, rel=1e-12)


# ---------------------------------------------------------------------------
# criterion 8 (FN-70): the request, field by field
# ---------------------------------------------------------------------------

# field -> (role of the node whose model uses it, accepted values, refused numbers)
FIELDS = {
    "q": ("fixed", [0, 0.5, 1, 1e-300, 0.05], [-0.1, 1.5, 1.0000001, -1e-300, 2, 101]),
    "lambda": ("rate", [0, 1e-6, 0.5, 1.5, 1e9], [-0.1, -1e-300, -1]),
    "T": ("rate", [1e-300, 0.5, 1.5, 8760], [0, -0.1, -1e-300]),
    "tau": ("standby", [1e-300, 0.5, 1.5, 720], [0, -0.1, -1e-300]),
    "mu": ("repairable", [0, 0.5, 1.5, 1e6], [-0.1, -1e-300, -1]),
}
FIELD_IDS = list(FIELDS)


def stored_value(doc, field):
    role = FIELDS[field][0]
    node = S.stored(doc[role])
    return node["probability"] if field == "q" else S.quant_of(doc[role])[field]


@pytest.mark.parametrize("field", FIELD_IDS)
def test_fn70_a_valid_number_is_accepted(client, doc, field):
    role, good, _bad = FIELDS[field]
    for value in good:
        payload = S.assert_ok(S.paste(client, [S.row(1, doc[role], **{field: value})]))
        assert payload["applied"] == 1 and payload["refused"] == [], (field, value)
        assert stored_value(doc, field) == value, (field, value)


@pytest.mark.parametrize("field", FIELD_IDS)
def test_fn70_a_number_out_of_range_is_400_invalid_field_naming_the_field(client, doc, field):
    role, _good, bad = FIELDS[field]
    for value in bad:
        before, depth = snapshot(), S.undo_depth()
        rows = [S.row(1, doc["fixed2"], q=0.77), S.row(7, doc[role], **{field: value})]
        error = S.assert_error(S.paste(client, rows), 400, "INVALID_FIELD", field)
        assert field in error["message"]
        assert error["detail"].get("clipRow") == 7, (field, value, error)
        assert_nothing_changed(before, depth)


@pytest.mark.parametrize("field", FIELD_IDS)
@pytest.mark.parametrize("value", ["0.1", "1e-6", "", " 0.5 ", True, False, None, [0.1], {"v": 0.1}],
                         ids=["str 0.1", "str 1e-6", "empty str", "padded str", "true", "false", "null", "list", "object"])
def test_fn70_a_string_bool_null_or_container_is_400_invalid_field(client, doc, field, value):
    role = FIELDS[field][0]
    before, depth = snapshot(), S.undo_depth()
    error = S.assert_error(S.paste(client, [S.row(3, doc[role], **{field: value})]), 400, "INVALID_FIELD", field)
    assert error["detail"].get("clipRow") == 3
    assert_nothing_changed(before, depth)


@pytest.mark.parametrize("field", FIELD_IDS)
@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_fn70_the_tokens_nan_and_infinity_are_400_invalid_json(client, doc, field, token):
    role = FIELDS[field][0]
    now = S.fields_now(client)
    raw = ('{"revision": %d, "documentSerial": %d, "rows": [{"clipRow": 1, "nodeId": "%s", "cells": {"%s": %s}}]}'
           % (now["revision"], now["documentSerial"], doc[role], field, token)).encode("utf-8")
    before, depth = snapshot(), S.undo_depth()
    S.assert_error(S.raw_paste(client, raw), 400, "INVALID_JSON")
    assert_nothing_changed(before, depth)


@pytest.mark.parametrize("field", FIELD_IDS)
def test_fn70_a_literal_beyond_the_float_range_is_400_invalid_field(client, doc, field):
    role = FIELDS[field][0]
    now = S.fields_now(client)
    raw = ('{"revision": %d, "documentSerial": %d, "rows": [{"clipRow": 1, "nodeId": "%s", "cells": {"%s": 1e999}}]}'
           % (now["revision"], now["documentSerial"], doc[role], field)).encode("utf-8")
    S.assert_error(S.raw_paste(client, raw), 400, "INVALID_FIELD", field)


@pytest.mark.parametrize("field", ["q", "lambda", "mu"])
@pytest.mark.parametrize("literal", ["-0", "-0.0", "-0e0"])
def test_fn70_negative_zero_is_stored_as_zero(client, doc, field, literal):
    role = FIELDS[field][0]
    now = S.fields_now(client)
    raw = ('{"revision": %d, "documentSerial": %d, "rows": [{"clipRow": 1, "nodeId": "%s", "cells": {"%s": %s}}]}'
           % (now["revision"], now["documentSerial"], doc[role], field, literal)).encode("utf-8")
    payload = S.assert_ok(S.raw_paste(client, raw))
    assert payload["applied"] == 1
    value = stored_value(doc, field)
    assert value == 0 and math.copysign(1.0, value) == 1.0, (field, literal, repr(value))


@pytest.mark.parametrize("field", ["T", "tau"])
def test_fn70_negative_zero_is_not_above_zero(client, doc, field):
    role = FIELDS[field][0]
    now = S.fields_now(client)
    raw = ('{"revision": %d, "documentSerial": %d, "rows": [{"clipRow": 1, "nodeId": "%s", "cells": {"%s": -0.0}}]}'
           % (now["revision"], now["documentSerial"], doc[role], field)).encode("utf-8")
    S.assert_error(S.raw_paste(client, raw), 400, "INVALID_FIELD", field)


@pytest.mark.parametrize("name", ["revision", "documentSerial"])
class TestRevisionFields:
    def _rows(self, doc):
        return [S.row(1, doc["fixed"], q=0.45)]

    def test_the_current_value_is_accepted(self, client, doc, name):
        S.assert_ok(S.paste(client, self._rows(doc)))

    @pytest.mark.parametrize("value", ["0", "1", -1, 1.5, 1.0, 0.0, True, False, None, [1], {"a": 1}],
                             ids=["str 0", "str 1", "negative", "1.5", "1.0", "0.0", "true", "false", "null", "list", "object"])
    def test_a_value_that_is_not_a_non_negative_integer_is_400(self, client, doc, name, value):
        before, depth = snapshot(), S.undo_depth()
        now = S.fields_now(client)
        payload = {"revision": now["revision"], "documentSerial": now["documentSerial"], "rows": self._rows(doc)}
        payload[name] = value
        error = S.assert_error(client.post(S.PASTE_URL, json=payload), 400, "INVALID_FIELD", name)
        assert name in error["message"]
        assert_nothing_changed(before, depth)

    def test_a_missing_value_is_400(self, client, doc, name):
        now = S.fields_now(client)
        payload = {"revision": now["revision"], "documentSerial": now["documentSerial"], "rows": self._rows(doc)}
        del payload[name]
        S.assert_error(client.post(S.PASTE_URL, json=payload), 400, "INVALID_FIELD", name)

    @pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
    def test_the_tokens_are_400_invalid_json(self, client, doc, name, token):
        now = S.fields_now(client)
        values = {"revision": str(now["revision"]), "documentSerial": str(now["documentSerial"])}
        values[name] = token
        raw = ('{"revision": %s, "documentSerial": %s, "rows": []}' % (values["revision"], values["documentSerial"])).encode()
        S.assert_error(S.raw_paste(client, raw), 400, "INVALID_JSON")


@pytest.mark.parametrize("raw", [b"[]", b'"text"', b"5", b"null", b"true", b"[{}]"],
                         ids=["list", "string", "number", "null", "bool", "list of object"])
def test_fn70_a_body_that_is_not_an_object_is_400_invalid_json(client, doc, raw):
    S.assert_error(S.raw_paste(client, raw), 400, "INVALID_JSON")


@pytest.mark.parametrize("raw", [b"", b"{", b"not json", b'{"revision": 1,', b"\xff\xfe"],
                         ids=["empty", "truncated", "text", "cut off", "not utf-8"])
def test_fn70_an_unreadable_body_is_400_invalid_json(client, doc, raw):
    S.assert_error(S.raw_paste(client, raw), 400, "INVALID_JSON")


def test_fn70_rows_must_be_a_list(client, doc):
    now = S.fields_now(client)
    for rows in ("x", {"clipRow": 1}, None, 5):
        payload = {"revision": now["revision"], "documentSerial": now["documentSerial"], "rows": rows}
        S.assert_error(client.post(S.PASTE_URL, json=payload), 400, "INVALID_FIELD", "rows")
    missing = {"revision": now["revision"], "documentSerial": now["documentSerial"]}
    S.assert_error(client.post(S.PASTE_URL, json=missing), 400, "INVALID_FIELD", "rows")


def test_fn70_an_unknown_cell_key_is_400_naming_cells(client, doc):
    before, depth = snapshot(), S.undo_depth()
    rows = [S.row(1, doc["fixed"], q=0.45), S.row(2, doc["rate"], colour="red")]
    S.assert_error(S.paste(client, rows), 400, "INVALID_FIELD", "cells")
    assert_nothing_changed(before, depth)


def test_fn70_a_key_of_the_json_node_that_is_not_a_grid_column_is_unknown_too(client, doc):
    for key in ("probability", "notes", "type", "mttr", "unc", "children", "Lambda", "LAMBDA", ""):
        S.assert_error(S.paste(client, [S.row(1, doc["rate"], **{key: 1})]), 400, "INVALID_FIELD", "cells")


def test_fn70_a_repeated_node_id_is_400_naming_rows(client, doc):
    before, depth = snapshot(), S.undo_depth()
    rows = [S.row(1, doc["fixed"], q=0.45), S.row(2, doc["fixed"], q=0.55)]
    S.assert_error(S.paste(client, rows), 400, "INVALID_FIELD", "rows")
    assert_nothing_changed(before, depth)


@pytest.mark.parametrize("rows", [
    [{"clipRow": 1, "nodeId": "a", "cells": {}}, {"clipRow": 1, "nodeId": "b", "cells": {}}],
    [{"clipRow": 0, "nodeId": "a", "cells": {}}],
    [{"clipRow": -1, "nodeId": "a", "cells": {}}],
    [{"clipRow": "1", "nodeId": "a", "cells": {}}],
    [{"clipRow": 1.5, "nodeId": "a", "cells": {}}],
    [{"nodeId": "a", "cells": {}}],
    [{"clipRow": 1, "nodeId": 5, "cells": {}}],
    [{"clipRow": 1, "cells": {}}],
    [{"clipRow": 1, "nodeId": "a", "cells": []}],
    ["row"],
    [None],
], ids=["dup clipRow", "zero", "negative", "str", "float", "no clipRow", "int nodeId", "no nodeId",
        "cells list", "row is str", "row is null"])
def test_fn70_a_malformed_row_is_400_invalid_field(client, doc, rows):
    S.assert_error(S.paste(client, rows), 400, "INVALID_FIELD")


@pytest.mark.parametrize("cells", [
    {"name": 5}, {"name": None}, {"source": 5}, {"tags": ["a"]}, {"id": 5}, {"model": 5}, {"model": "bogus"},
    {"model": ""}, {"model": None},
], ids=["name int", "name null", "source int", "tags list", "id int", "model int", "model bogus", "model empty",
        "model null"])
def test_fn70_a_text_cell_of_the_wrong_type_or_an_unknown_model_is_400(client, doc, cells):
    before, depth = snapshot(), S.undo_depth()
    key = next(iter(cells))
    S.assert_error(S.paste(client, [S.row(1, doc["fixed"], **cells)]), 400, "INVALID_FIELD",
                   "model" if key == "model" else None)
    assert_nothing_changed(before, depth)


def test_fn70_eta_mode_is_not_supported(client, doc):
    assert client.post("/api/metadata", json={"mode": "ETA"}).status_code == 200
    before, depth = snapshot(), S.undo_depth()
    response = S.paste(client, [S.row(1, doc["fixed"], q=0.45)])
    assert response.status_code == 409, response.status_code
    assert S.body(response)["error"]["code"] == "MODE_UNSUPPORTED"
    assert_nothing_changed(before, depth)


def test_fn70_eta_mode_is_checked_before_the_revision(client, doc):
    assert client.post("/api/metadata", json={"mode": "ETA"}).status_code == 200
    now = S.fields_now(client)
    response = S.paste(client, [S.row(1, doc["fixed"], q=0.45)], revision=now["revision"] + 3)
    assert response.status_code == 409, response.status_code
    assert S.body(response)["error"]["code"] == "MODE_UNSUPPORTED"


# ---------------------------------------------------------------------------
# validators of grid_schema, imported inside the tests (module absent until T1)
# ---------------------------------------------------------------------------


def _call(validator, value, field):
    import inspect

    params = [p for p in inspect.signature(validator).parameters.values()
              if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) and p.default is p.empty]
    return validator(value, field) if len(params) >= 2 else validator(value)


@pytest.mark.parametrize("name, field, good, bad", [
    ("validate_grid_q", "q", [0, 0.5, 1], [-0.1, 1.5, "0.1", None, True]),
    ("validate_grid_lambda", "lambda", [0, 1e-6, 5], [-0.1, "0.1", None, True]),
    ("validate_grid_duration", "T", [1e-300, 8760], [0, -0.1, "0.1", None, True]),
    ("validate_grid_duration", "tau", [1e-300, 720], [0, -0.1, "0.1", None, True]),
    ("validate_grid_mu", "mu", [0, 0.5, 3], [-0.1, "0.1", None, True]),
])
def test_validator_ranges_and_field_names(name, field, good, bad):
    from fta_web import grid_schema
    from fta_web.errors import ApiError

    validator = getattr(grid_schema, name)
    for value in good:
        assert _call(validator, value, field) == value
    for value in bad:
        with pytest.raises(ApiError) as caught:
            _call(validator, value, field)
        assert caught.value.code == "INVALID_FIELD" and caught.value.status == 400
        assert caught.value.detail.get("field") == field


@pytest.mark.parametrize("name, field", [
    ("validate_grid_q", "q"), ("validate_grid_lambda", "lambda"), ("validate_grid_duration", "T"),
    ("validate_grid_mu", "mu")])
def test_validators_refuse_nan_infinity_and_return_positive_zero_for_negative_zero(name, field):
    from fta_web import grid_schema
    from fta_web.errors import ApiError

    validator = getattr(grid_schema, name)
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(ApiError):
            _call(validator, value, field)
    if field != "T":
        zero = _call(validator, -0.0, field)
        assert zero == 0 and math.copysign(1.0, zero) == 1.0


def test_grid_schema_constants():
    from fta_web import grid_schema

    assert grid_schema.MAX_PASTE_ROWS == 2000
    assert list(grid_schema.GRID_COLUMNS) == ["id", "name", "model", "lambda", "T", "tau", "mu", "q", "source", "tags"]


# ---------------------------------------------------------------------------
# existing routes and validators are unchanged (these pass before and after F3)
# ---------------------------------------------------------------------------


def test_existing_routes_the_node_update_route_reads_as_it_did(client, doc):
    node = doc["fixed"]
    # lenient reading kept: a numeric string is a probability on the old route (the grid endpoint refuses it)
    assert client.patch("/api/nodes/" + node, json={"probability": "0.25"}).status_code == 200
    assert S.stored(node)["probability"] == 0.25
    for payload, code, field in [
        ({"probability": 1.5}, "INVALID_FIELD", "probability"),
        ({"probability": -0.1}, "INVALID_FIELD", "probability"),
        ({"quant": {"lambda": -1}}, "INVALID_FIELD", "quant.lambda"),
        ({"quant": {"T": 0}}, "INVALID_FIELD", "quant.T"),
        ({"quant": {"tau": 0}}, "INVALID_FIELD", "quant.tau"),
        ({"quant": {"mu": -1}}, "INVALID_FIELD", "quant.mu"),
        ({"quant": {"lambda": "1e-3"}}, "INVALID_FIELD", "quant.lambda"),
    ]:
        error = S.assert_error(client.patch("/api/nodes/" + node, json=payload), 400, code, field)
        assert field in error["message"] or field.split(".")[-1] in error["message"]
    nan_body = b'{"probability": NaN}'
    assert client.patch("/api/nodes/" + node, data=nan_body, content_type="application/json").status_code == 400


def test_existing_routes_accept_what_they_accepted(client, doc):
    node = doc["rate"]
    ok = client.patch("/api/nodes/" + node, json={"quant": {"lambda": 2.5e-6, "T": 10, "source": "s"},
                                                  "trace": {"tags": ["a", "b"]}, "name": " Renamed  event "})
    assert ok.status_code == 200
    assert S.stored(node)["name"] == "Renamed event"
    assert S.quant_of(node)["lambda"] == 2.5e-6
    created = client.post("/api/nodes", json={"parentId": "root", "name": "New", "probability": 0.5})
    assert created.status_code == 200


# ---------------------------------------------------------------------------
# the PERF-6 sheet through the endpoint: 500 rows, one undo step (server side of G4)
# ---------------------------------------------------------------------------


def test_the_perf_sheet_of_500_rows_is_one_undo_step(client, tmp_path):
    import shutil

    target = tmp_path / "perf_grid_500.json"
    shutil.copyfile(S.FIXTURES / "perf_grid_500.json", target)
    assert client.post("/api/file/open", json={"path": str(target), "force": True}).status_code == 200
    ids = ["E%02d_%02d" % (g, n) for g in range(25) for n in range(20)]
    lines = (S.FIXTURES / "perf_grid_500_paste.tsv").read_text(encoding="utf-8").split("\n")
    lines = [line for line in lines if line]
    assert len(lines) == len(ids) == 500
    rows = []
    for index, (node_id, line) in enumerate(zip(ids, lines)):
        lam_year, hours, source = line.split("\t")
        rows.append(S.row(index + 1, node_id, **{"lambda": float(lam_year) / 8760, "T": float(hours), "source": source}))
    before, depth = snapshot(), S.undo_depth()
    payload = S.assert_ok(S.paste(client, rows))
    assert payload["applied"] == 500 and payload["refused"] == []
    assert S.undo_depth() == depth + 1
    assert S.quant_of("E00_01")["source"] == "perf-E00_01"
    assert S.quant_of("E00_01")["lambda"] == pytest.approx(0.009636 / 8760, rel=1e-12)
    assert client.post("/api/undo").status_code == 200
    assert snapshot() == before
