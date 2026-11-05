"""F4 BRIEF criterion 7 (FN-70 for ``factor``, 409, no state change): ``POST /api/whatif``.

Table of DESIGN 3.1 and the order of its checks:

    JSON -> revision -> documentSerial -> factors shape -> every factor value (request order)
    -> ETA (409 MODE_UNSUPPORTED) -> stale (409 STALE_REVISION) -> ids -> group conflict
    -> evaluability (422 WHATIF_NOT_EVALUABLE)

Every refusal leaves the document alone: ``revision``, ``documentSerial``, ``canUndo``,
``canRedo``, ``dirty``, the undo depth and ``state.snapshot()`` are identical before and after.
Until the route exists each test fails on the 404 of ``POST /api/whatif``.
"""
import json

import pytest

import whatif_support as W

URL = W.URL
OMIT = W.OMIT


def body_text(api, revision=None, serial=None, factors="{}", extra=""):
    """A request body as exact text. ``revision`` / ``serial`` / ``factors`` are JSON texts;
    None means the current value, ``OMIT`` leaves the key out."""
    fields = api.fields()
    parts = []
    if revision is not OMIT:
        parts.append('"revision": %s' % (fields["revision"] if revision is None else revision))
    if serial is not OMIT:
        parts.append('"documentSerial": %s' % (fields["documentSerial"] if serial is None else serial))
    if factors is not OMIT:
        parts.append('"factors": %s' % factors)
    if extra:
        parts.append(extra)
    return "{%s}" % ", ".join(parts)


def post_text(api, text):
    return api.raw("POST", URL, text)


@pytest.fixture
def eta(api):
    api.open_doc(W.models_doc())
    status, body = api.post("/api/metadata", {"mode": "ETA"})
    assert status == 200, body
    return api


# --------------------------------------------------------------- registration


def test_the_route_is_registered_in_the_real_app_for_post():
    from fta_web.app import create_app

    rules = [rule for rule in create_app().url_map.iter_rules() if rule.rule == URL]
    assert rules, "POST /api/whatif is not registered (app._BLUEPRINTS)"
    assert "POST" in set().union(*(rule.methods for rule in rules))


def test_the_route_needs_the_session_token_like_every_api_route(tmp_path):
    """Real app with the security layer: no token -> 403; the token -> 200."""
    from fta_web import config
    from fta_web.app import create_app

    token = "f4-test-token-0123456789-abcdefghijklmnopqrstuvwxyz"
    port = 8784
    base = "http://127.0.0.1:%d" % port
    app = create_app(token=token, port=port, fs_root=tmp_path)
    client = app.test_client()
    header = {config.TOKEN_HEADER: token}

    revision = client.get("/api/revision", base_url=base, headers=header).get_json()
    payload = {"revision": revision["revision"], "documentSerial": revision["documentSerial"],
               "factors": {}}
    refused = client.post(URL, json=payload, base_url=base)
    assert refused.status_code == 403, refused.status_code
    accepted = client.post(URL, json=payload, base_url=base, headers=header)
    assert accepted.status_code == 200, accepted.get_data(as_text=True)[:300]
    assert accepted.get_json()["ok"] is True


# ------------------------------------------------------------------- FN-70: f

ACCEPTED_FACTORS = ["10", "10.0", "1", "0.01", "100", "100.0", "1e1", "1E1", "0.5", "1e-2", "12.5",
                    "0.010000000000000002", "99.99999999"]
#: (JSON text for f) -> INVALID_FIELD naming "factor"
REFUSED_FACTORS = ['"0.1"', '"10"', '"abc"', '""', "-0.1", "101", "100.0001", "0.009", "0.0099999",
                   "0", "0.0", "-0", "-0.0", "-1", "true", "false", "null", "[10]", "[]",
                   '{"f": 10}', "1e999", "-1e999", "1e309"]
TOKEN_FACTORS = ["NaN", "Infinity", "-Infinity"]


@pytest.mark.parametrize("text", ACCEPTED_FACTORS)
def test_a_number_inside_0_01_to_100_is_accepted(r1, text):
    status, body = r1.raw_with('{"A": %s}' % text)
    assert status == 200, body
    assert body["ok"] is True
    assert body["events"][0]["id"] == "A"
    assert body["events"][0]["factor"] == json.loads(text)


@pytest.mark.parametrize("text", REFUSED_FACTORS)
def test_a_bad_factor_is_invalid_field_naming_factor_and_the_event(r1, text):
    before = W.fingerprint()
    err = W.assert_error(r1.raw_with('{"A": %s}' % text), 400, "INVALID_FIELD", field="factor")
    assert err["detail"]["id"] == "A"
    assert "factor" in err["message"]
    assert W.fingerprint() == before


def _call_validator(validator, value, field="factor"):
    """The validator with one or two positional arguments, whichever it takes (as F3's tests)."""
    import inspect

    params = [p for p in inspect.signature(validator).parameters.values()
              if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) and p.default is p.empty]
    return validator(value, field) if len(params) >= 2 else validator(value)


def test_validate_whatif_factor_accepts_the_range_and_refuses_the_rest():
    """FN-70 table: ``fta_web.whatif_schema.validate_whatif_factor`` (module and name from DESIGN
    3.1), as ``grid_schema`` has validators for the grid fields. Refusals are
    ``INVALID_FIELD``, 400, naming the field ``factor``."""
    from fta_web.errors import ApiError
    from fta_web.whatif_schema import validate_whatif_factor

    for value in (0.01, 1, 100):
        assert _call_validator(validate_whatif_factor, value) == value
    for value in (0.009, 101, "0.1", True, None):
        with pytest.raises(ApiError) as caught:
            _call_validator(validate_whatif_factor, value)
        assert caught.value.code == "INVALID_FIELD" and caught.value.status == 400
        assert caught.value.detail.get("field") == "factor"


def _spy_on_the_validator(monkeypatch, refuse=()):
    """Replace ``validate_whatif_factor`` wherever the route or the module may hold it (the
    schema module, and any other module that imported the name) by a spy that records the values
    it is given and refuses those in ``refuse``. Returns the list of recorded values."""
    import sys

    from fta_web import whatif_schema
    from fta_web.errors import ApiError

    real = whatif_schema.validate_whatif_factor
    seen = []

    def spy(value, *args, **kwargs):
        seen.append(value)
        if value in refuse:
            raise ApiError("INVALID_FIELD", "spy: this factor is refused", 400, {"field": "factor"})
        return real(value, *args, **kwargs)

    monkeypatch.setattr(whatif_schema, "validate_whatif_factor", spy)
    for name in ("fta_web.routes.whatif", "fta_web.whatif"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "validate_whatif_factor", None) is real:
            monkeypatch.setattr(module, "validate_whatif_factor", spy)
    return seen


def test_the_endpoint_checks_every_factor_with_validate_whatif_factor(r1, monkeypatch):
    """The route must use the shared validator (so an inline check cannot satisfy FN-70): a spy
    sees every value of the request, in request order."""
    seen = _spy_on_the_validator(monkeypatch)
    status, body = r1.raw_with('{"A": 10, "B": 10, "C": 0.5}')
    assert status == 200, body
    assert seen == [10, 10, 0.5]


def test_a_refusal_by_validate_whatif_factor_is_the_answer_of_the_endpoint(r1, monkeypatch):
    """A validator that refuses 7 makes the endpoint refuse 7, though 7 is inside 0.01..100: the
    decision is the validator's, not an inline range check."""
    seen = _spy_on_the_validator(monkeypatch, refuse=(7,))
    err = W.assert_error(r1.raw_with('{"A": 7}'), 400, "INVALID_FIELD", field="factor")
    assert "spy" in err["message"]
    assert seen == [7]


@pytest.mark.parametrize("token", TOKEN_FACTORS)
def test_the_tokens_nan_and_infinity_are_invalid_json(r1, token):
    before = W.fingerprint()
    W.assert_error(r1.raw_with('{"A": %s}' % token), 400, "INVALID_JSON")
    assert W.fingerprint() == before


def test_a_token_anywhere_in_the_body_is_invalid_json(r1):
    W.assert_error(post_text(r1, body_text(r1, extra='"note": NaN')), 400, "INVALID_JSON")
    W.assert_error(post_text(r1, body_text(r1, revision="Infinity")), 400, "INVALID_JSON")


def test_nan_inside_a_string_is_just_text_an_event_id_called_nan_is_an_unknown_event(r1):
    W.assert_error(r1.raw_with('{"NaN": 10}'), 400, "INVALID_FIELD", field="factors",
                   reason="unknown_event", id="NaN")


def test_the_first_bad_factor_in_request_order_is_the_one_reported(r1):
    err = W.assert_error(r1.raw_with('{"B": "x", "A": 200}'), 400, "INVALID_FIELD", field="factor")
    assert err["detail"]["id"] == "B"
    err = W.assert_error(r1.raw_with('{"A": 200, "B": "x"}'), 400, "INVALID_FIELD", field="factor")
    assert err["detail"]["id"] == "A"


@pytest.mark.parametrize("raw", ["[]", "[10]", '"text"', "not json", "", "{", "{'a': 1}", "null", "10"])
def test_a_body_that_is_not_a_json_object_is_invalid_json(r1, raw):
    W.assert_error(r1.raw("POST", URL, raw), 400, "INVALID_JSON")


def test_the_content_type_does_not_matter(r1):
    text = body_text(r1, factors='{"A": 10}')
    response = r1.client.post(URL, data=text.encode("utf-8"), content_type="text/plain")
    assert response.status_code == 200, response.get_data(as_text=True)[:300]


# ------------------------------------------- revision, documentSerial, factors

BAD_REVISIONS = ['"1"', "-1", "1.0", "1.5", "true", "null", "[]", "1e2"]


@pytest.mark.parametrize("text", BAD_REVISIONS)
def test_a_bad_revision_names_the_field(r1, text):
    W.assert_error(post_text(r1, body_text(r1, revision=text)), 400, "INVALID_FIELD", field="revision")


def test_a_missing_revision_is_invalid_field(r1):
    W.assert_error(post_text(r1, body_text(r1, revision=OMIT)), 400, "INVALID_FIELD", field="revision")


@pytest.mark.parametrize("text", ['"1"', "-1", "1.0", "1.5", "true", "[]"])
def test_a_bad_document_serial_names_the_field(r1, text):
    W.assert_error(post_text(r1, body_text(r1, serial=text)), 400, "INVALID_FIELD",
                   field="documentSerial")


def test_document_serial_is_optional(r1):
    """SPEC 7.5 shows only ``revision``: without the serial the revision decides."""
    status, body = post_text(r1, body_text(r1, serial=OMIT))
    assert status == 200, body
    stale = post_text(r1, body_text(r1, serial=OMIT, revision="%d" % (r1.fields()["revision"] + 1)))
    W.assert_error(stale, 409, "STALE_REVISION")


@pytest.mark.parametrize("text", ['[]', '[1]', '"x"', "null", "5", "true"])
def test_factors_must_be_an_object(r1, text):
    W.assert_error(post_text(r1, body_text(r1, factors=text)), 400, "INVALID_FIELD", field="factors")


def test_factors_is_required(r1):
    W.assert_error(post_text(r1, body_text(r1, factors=OMIT)), 400, "INVALID_FIELD", field="factors")


def test_an_empty_factors_object_is_accepted(r1):
    body = r1.whatif_ok({})
    assert body["events"] == [] and body["whatIf"] == body["baseline"]


def test_at_most_1000_factors_1000_pass_the_shape_check_1001_do_not(r1):
    thousand = {"E%d" % i: 10 for i in range(1000)}
    err = W.assert_error(r1.whatif(thousand), 400, "INVALID_FIELD", field="factors")
    assert err["detail"].get("reason") == "unknown_event"  # past the shape check, then the ids
    too_many = dict(thousand, E1000=10)
    err = W.assert_error(r1.whatif(too_many), 400, "INVALID_FIELD", field="factors")
    assert err["detail"].get("reason") != "unknown_event"


# ------------------------------------------------------------ the order of checks


def test_order_json_first(r1):
    W.assert_error(post_text(r1, '{"revision": "x", "documentSerial": -1, "factors": NaN}'), 400,
                   "INVALID_JSON")


def test_order_revision_before_document_serial_before_factors(r1):
    both = body_text(r1, revision='"x"', serial='"y"', factors="[]")
    W.assert_error(post_text(r1, both), 400, "INVALID_FIELD", field="revision")
    no_revision = body_text(r1, serial='"y"', factors="[]")
    W.assert_error(post_text(r1, no_revision), 400, "INVALID_FIELD", field="documentSerial")


def test_order_validation_before_stale(r1):
    """A bad factor or a bad factors shape wins over a stale revision."""
    old = r1.fields()["revision"] + 5
    W.assert_error(post_text(r1, body_text(r1, revision=str(old), factors='{"A": "x"}')), 400,
                   "INVALID_FIELD", field="factor")
    W.assert_error(post_text(r1, body_text(r1, revision=str(old), factors="[]")), 400,
                   "INVALID_FIELD", field="factors")


def test_order_factor_values_before_eta(eta):
    W.assert_error(eta.whatif({"RATE": 1000}), 400, "INVALID_FIELD", field="factor")
    W.assert_error(eta.whatif({"RATE": 10}), 409, "MODE_UNSUPPORTED")


def test_order_eta_before_stale(eta):
    stale = eta.fields()["revision"] + 5
    err = W.assert_error(eta.whatif({"RATE": 10}, revision=stale), 409, "MODE_UNSUPPORTED")
    assert err["detail"]["mode"] == "ETA"


def test_order_stale_before_ids(r1):
    stale = r1.fields()["revision"] + 5
    W.assert_error(r1.whatif({"ghost": 10}, revision=stale), 409, "STALE_REVISION")
    wrong_serial = r1.fields()["documentSerial"] + 5
    W.assert_error(r1.whatif({"ghost": 10}, documentSerial=wrong_serial), 409, "STALE_REVISION")


def test_order_ids_before_group_conflict(r1):
    W.assert_error(r1.whatif({"A": 10, "B": 5, "ghost": 10}), 400, "INVALID_FIELD", field="factors",
                   reason="unknown_event", id="ghost")
    W.assert_error(r1.raw_with('{"ghost": 10, "A": 10, "B": 5}'), 400, "INVALID_FIELD",
                   field="factors", reason="unknown_event", id="ghost")
    W.assert_error(r1.raw_with('{"B": 5, "ghost": 10, "A": 10}'), 400, "INVALID_FIELD",
                   field="factors", reason="unknown_event", id="ghost")


def test_order_ids_before_evaluability(api):
    api.open_doc(W.missing_param_doc())
    W.assert_error(api.whatif({"BAD": 10, "ghost": 10}), 400, "INVALID_FIELD", field="factors",
                   reason="unknown_event", id="ghost")


# ------------------------------------------------------------------ 409 stale


def test_a_stale_revision_is_409_with_the_current_numbers(r1):
    now = r1.fields()
    err = W.assert_error(r1.whatif({"A": 10}, revision=now["revision"] + 1), 409, "STALE_REVISION")
    assert err["detail"] == {"revision": now["revision"], "documentSerial": now["documentSerial"]}
    assert "The document changed" in err["message"]


def test_an_older_revision_is_stale_too(r1):
    r1.edit("C", name="Renamed C")
    now = r1.fields()
    assert now["revision"] >= 1
    err = W.assert_error(r1.whatif({"A": 10}, revision=now["revision"] - 1), 409, "STALE_REVISION")
    assert err["detail"]["revision"] == now["revision"]


def test_a_stale_document_serial_is_409(r1):
    now = r1.fields()
    err = W.assert_error(r1.whatif({"A": 10}, documentSerial=now["documentSerial"] + 1), 409,
                         "STALE_REVISION")
    assert err["detail"]["documentSerial"] == now["documentSerial"]


def test_the_current_version_is_not_stale(r1):
    now = r1.fields()
    body = r1.whatif_ok({"A": 10})
    assert body["revision"] == now["revision"] and body["documentSerial"] == now["documentSerial"]


# ------------------------------------------------------------------- ETA mode


def test_eta_mode_is_409_mode_unsupported(eta):
    err = W.assert_error(eta.whatif({"RATE": 10}), 409, "MODE_UNSUPPORTED")
    assert err["detail"]["mode"] == "ETA"
    err = W.assert_error(eta.whatif({}), 409, "MODE_UNSUPPORTED")
    assert err["detail"]["mode"] == "ETA"


# ----------------------------------------------------------------------- ids


def test_an_id_that_is_not_in_the_tree(r1):
    err = W.assert_error(r1.whatif({"ghost": 10}), 400, "INVALID_FIELD", field="factors",
                         reason="unknown_event", id="ghost")
    assert "ghost" in json.dumps(err["detail"])


@pytest.mark.parametrize("node_id", ["root", "G1", "H", "SUB", "XF"])
def test_a_gate_the_root_a_house_event_or_a_transfer_is_not_a_basic_event(api, node_id):
    """root, G1 (gate), SUB (gate), H (house event), XF (transfer gate)."""
    api.open_doc(W.special_doc())
    W.assert_error(api.whatif({node_id: 10}), 400, "INVALID_FIELD", field="factors",
                   reason="not_basic_event", id=node_id)


def test_a_basic_event_of_that_tree_is_fine(api):
    api.open_doc(W.special_doc())
    body = api.whatif_ok({"C": 10})
    assert [r["id"] for r in body["events"]] == ["C"]


def test_a_factor_of_1_on_a_gate_is_still_refused(api):
    api.open_doc(W.special_doc())
    W.assert_error(api.whatif({"G1": 1}), 400, "INVALID_FIELD", field="factors",
                   reason="not_basic_event", id="G1")


# --------------------------------------------------------------- evaluability


def test_an_event_with_a_missing_parameter_and_a_factor_is_422(api):
    api.open_doc(W.missing_param_doc())
    err = W.assert_error(api.whatif({"BAD": 10}), 422, "WHATIF_NOT_EVALUABLE")
    assert err["detail"]["id"] == "BAD"
    assert "lambda" in err["detail"]["missing"]


def test_the_same_event_with_factor_1_gets_a_row_that_says_it_is_not_evaluable(api):
    api.open_doc(W.missing_param_doc())
    body = api.whatif_ok({"BAD": 1})
    row = W.row_of(body, "BAD")
    assert row["evaluable"] is False
    assert row["q"] is None and row["nominalQ"] is None
    assert body["whatIf"] == body["baseline"]


def test_an_evaluable_event_next_to_a_broken_one_is_still_scaled(api):
    api.open_doc(W.missing_param_doc())
    body = api.whatif_ok({"OK": 10, "BAD": 1})
    assert W.row_of(body, "OK")["q"] == W.rel(1e-2, 1e-9)
    assert W.row_of(body, "OK")["evaluable"] is True


# ----------------------------------------------------------- no state change


def _two_edits_and_an_undo(api):
    api.edit("C", name="C first")
    api.edit("C", name="C second")
    status, body = api.post("/api/undo")
    assert status == 200, body


CALLS = [
    ("ok", lambda api: api.whatif({"A": 10})),
    ("ok_empty", lambda api: api.whatif({})),
    ("ok_nothing_changes", lambda api: api.whatif({"C": 10})),
    ("bad_factor", lambda api: api.raw_with('{"A": "0.1"}')),
    ("nan", lambda api: api.raw_with('{"A": NaN}')),
    ("out_of_range", lambda api: api.whatif({"A": 101})),
    ("bad_revision", lambda api: api.whatif({"A": 10}, revision="x")),
    ("stale", lambda api: api.whatif({"A": 10}, revision=10 ** 6)),
    ("stale_serial", lambda api: api.whatif({"A": 10}, documentSerial=10 ** 6)),
    ("unknown_id", lambda api: api.whatif({"ghost": 10})),
    ("not_basic", lambda api: api.whatif({"G1": 10})),
    ("group_conflict", lambda api: api.whatif({"A": 10, "B": 5})),
    ("not_an_object", lambda api: api.raw("POST", URL, "[]")),
]


@pytest.mark.parametrize("name, call", CALLS, ids=[c[0] for c in CALLS])
def test_no_call_changes_the_document_its_history_or_the_flags(r1, name, call):
    _two_edits_and_an_undo(r1)
    before = W.fingerprint()
    assert before["canUndo"] is True and before["canRedo"] is True and before["dirty"] is True
    status, body = call(r1)
    assert status in (200, 400, 409, 422), (status, body)
    assert W.fingerprint() == before
    # the HTTP view of the same facts
    assert r1.fields() == {"revision": before["revision"], "documentSerial": before["documentSerial"]}
    state = r1.get("/api/state")[1]
    assert state["canUndo"] is True and state["canRedo"] is True and state["dirty"] is True


def test_no_call_changes_the_state_in_eta_or_for_a_broken_event(api):
    api.open_doc(W.missing_param_doc())
    before = W.fingerprint()
    W.assert_error(api.whatif({"BAD": 10}), 422, "WHATIF_NOT_EVALUABLE")
    api.whatif_ok({"OK": 10})
    assert W.fingerprint() == before
    status, body = api.post("/api/metadata", {"mode": "ETA"})
    assert status == 200, body
    before = W.fingerprint()
    W.assert_error(api.whatif({"OK": 10}), 409, "MODE_UNSUPPORTED")
    assert W.fingerprint() == before


def test_a_run_of_calls_does_not_add_an_undo_step(r1):
    r1.edit("C", name="C only edit")
    depth = W.fingerprint()["undoDepth"]
    for factors in ({"A": 10}, {"A": 0.5}, {"B": 100}, {}):
        r1.whatif_ok(factors)
    assert W.fingerprint()["undoDepth"] == depth
    status, body = r1.post("/api/undo")
    assert status == 200
    assert r1.get("/api/nodes/C")[1]["node"]["name"] != "C only edit"


def test_the_live_tree_keeps_its_nominal_values_after_a_call(r1):
    """A call with f = 10 leaves the stored q of A and B at 1e-3 (the nominal tree)."""
    r1.whatif_ok({"A": 10})
    for node_id in ("A", "B"):
        node = r1.get("/api/nodes/%s" % node_id)[1]["node"]
        assert node["probability"] == W.rel(1e-3, 1e-12)
    assert r1.headline() == W.rel(W.R1_BASELINE, 1e-9)
