"""F0 BRIEF criterion 1: ``fta_web/strict_input.py`` (the shared part of FN-70).

``read_strict_json(request)``, ``number_field(value, field, lo, hi, *, lo_open,
hi_open)`` and ``validate_revision(value, field)`` are tested directly and on
the wire through a throwaway Flask app that registers the same ``ApiError``
handler as the real app. The module must change nothing else: no route, no
app-wide JSON provider.

The module is imported inside each test, so that until it exists every test
fails with ``ModuleNotFoundError`` and with nothing else.
"""
import importlib
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]


def strict_input():
    return importlib.import_module("fta_web.strict_input")


def api_error_class():
    return importlib.import_module("fta_web.errors").ApiError


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def read_body(raw, content_type="application/json"):
    """``read_strict_json`` called on a real Flask request holding ``raw``."""
    import flask

    app = flask.Flask(__name__)
    with app.test_request_context("/x", method="POST", data=raw, content_type=content_type):
        return strict_input().read_strict_json(flask.request)


def assert_api_error(exc_info, code, field=None):
    err = exc_info.value
    assert err.code == code
    assert err.status == 400
    assert isinstance(err.message, str) and err.message
    if field is not None:
        assert field in err.message
        assert err.detail.get("field") == field
    return err


@pytest.fixture
def wire():
    """A throwaway app with one route per helper and the real error handler."""
    import flask

    errors = importlib.import_module("fta_web.errors")
    si = strict_input()
    app = flask.Flask(__name__)

    @app.errorhandler(errors.ApiError)
    def _handle(err):
        return errors.api_error_response(err)

    @app.post("/json")
    def echo():
        return flask.jsonify({"ok": True, "body": si.read_strict_json(flask.request)})

    @app.post("/number")
    def number():
        body = si.read_strict_json(flask.request)
        return flask.jsonify({"ok": True, "v": si.number_field(body.get("v"), "v", 0.01, 100)})

    @app.post("/open")
    def open_bounds():
        body = si.read_strict_json(flask.request)
        value = si.number_field(body.get("v"), "v", 0, 1, lo_open=True, hi_open=True)
        return flask.jsonify({"ok": True, "v": value})

    @app.post("/revision")
    def revision():
        body = si.read_strict_json(flask.request)
        return flask.jsonify({"ok": True, "r": si.validate_revision(body.get("r"), "revision")})

    with app.test_client() as client:
        yield client


def post(client, path, raw):
    response = client.post(path, data=raw, content_type="application/json")
    return response, json.loads(response.get_data(as_text=True))


def assert_envelope(response, payload, code, field=None):
    assert response.status_code == 400
    assert payload["ok"] is False
    error = payload["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    if field is not None:
        assert field in error["message"]
        assert error["detail"]["field"] == field


# --------------------------------------------------------------------------
# read_strict_json: the tokens NaN, Infinity, -Infinity
# --------------------------------------------------------------------------

BAD_TOKEN_BODIES = [
    b"NaN",
    b"Infinity",
    b"-Infinity",
    b'{"v": NaN}',
    b'{"v": Infinity}',
    b'{"v": -Infinity}',
    b'[NaN]',
    b'[1, 2, Infinity]',
    b'{"a": {"b": {"c": -Infinity}}}',
    b'{"a": [1, {"b": NaN}]}',
    b'{"rows": [{"cells": {"q": NaN}}, {"cells": {"q": 0.5}}]}',
    b'{"factors": {"n1": Infinity}}',
]


@pytest.mark.parametrize("raw", BAD_TOKEN_BODIES)
def test_read_strict_json_refuses_nan_and_infinity_tokens(raw):
    ApiError = api_error_class()
    with pytest.raises(ApiError) as exc_info:
        read_body(raw)
    assert_api_error(exc_info, "INVALID_JSON")


@pytest.mark.parametrize("raw", [
    b"",
    b"   ",
    b"not json",
    b"{",
    b'{"a": 1',
    b'{"a": [1, 2',
    b'{"a": }',
    b"{'a': 1}",
    b'{"a": 1,}',
    b"\x80\x81\x82",
])
def test_read_strict_json_refuses_a_body_that_is_not_json(raw):
    ApiError = api_error_class()
    with pytest.raises(ApiError) as exc_info:
        read_body(raw)
    assert_api_error(exc_info, "INVALID_JSON")


def test_read_strict_json_returns_the_parsed_object():
    body = {"revision": 3, "factors": {"n1": 2.5, "n2": 0}, "rows": [{"q": 1e-3}, None, True],
            "text": "ok"}
    assert read_body(json.dumps(body).encode("utf-8")) == body


def test_read_strict_json_accepts_the_token_words_inside_strings():
    body = {"name": "NaN", "other": "Infinity", "third": "-Infinity", "k": ["NaN"]}
    assert read_body(json.dumps(body).encode("utf-8")) == body


def test_read_strict_json_reads_ordinary_numbers_untouched():
    body = read_body(b'{"i": 7, "f": 0.1, "e": 1e-3, "neg": -2.5, "z": 0}')
    assert body == {"i": 7, "f": 0.1, "e": 1e-3, "neg": -2.5, "z": 0}
    assert isinstance(body["i"], int) and isinstance(body["f"], float)


@pytest.mark.parametrize("raw", BAD_TOKEN_BODIES[:6] + [b"", b"nope", b'{"a": 1'])
def test_wire_invalid_json_envelope(wire, raw):
    response, payload = post(wire, "/json", raw)
    assert_envelope(response, payload, "INVALID_JSON")


def test_wire_valid_json_passes_through(wire):
    response, payload = post(wire, "/json", b'{"a": [1, 2.5, "NaN"]}')
    assert response.status_code == 200
    assert payload == {"ok": True, "body": {"a": [1, 2.5, "NaN"]}}


# --------------------------------------------------------------------------
# number_field
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0.01, 0.5, 1, 1.5, 50, 99.99, 100, 100.0])
def test_number_field_accepts_numbers_in_a_closed_range(value):
    result = strict_input().number_field(value, "factor", 0.01, 100)
    assert result == value


def test_number_field_accepts_ints_and_floats_at_both_bounds():
    si = strict_input()
    assert si.number_field(0, "q", 0, 1) == 0
    assert si.number_field(1, "q", 0, 1) == 1
    assert si.number_field(0.0, "q", 0, 1) == 0
    assert si.number_field(1.0, "q", 0, 1) == 1


def test_number_field_accepts_an_unbounded_upper_end():
    """FN-70 table: lambda is >= 0 with no upper bound (hi = infinity)."""
    si = strict_input()
    assert si.number_field(1e300, "lambda", 0, math.inf) == 1e300
    assert si.number_field(0, "lambda", 0, math.inf) == 0


@pytest.mark.parametrize("value, field", [(0.0, "T"), (0, "T"), (-0.0, "T")])
def test_number_field_open_lower_bound_refuses_the_bound(value, field):
    ApiError = api_error_class()
    with pytest.raises(ApiError) as exc_info:
        strict_input().number_field(value, field, 0, math.inf, lo_open=True)
    assert_api_error(exc_info, "INVALID_FIELD", field)


def test_number_field_open_lower_bound_accepts_just_inside():
    assert strict_input().number_field(1e-300, "T", 0, math.inf, lo_open=True) == 1e-300
    assert strict_input().number_field(5e-324, "T", 0, math.inf, lo_open=True) == 5e-324


def test_number_field_open_upper_bound_refuses_the_bound_and_accepts_just_inside():
    si = strict_input()
    ApiError = api_error_class()
    with pytest.raises(ApiError) as exc_info:
        si.number_field(1, "q", 0, 1, hi_open=True)
    assert_api_error(exc_info, "INVALID_FIELD", "q")
    with pytest.raises(ApiError):
        si.number_field(1.0, "q", 0, 1, hi_open=True)
    below = math.nextafter(1.0, 0.0)
    assert si.number_field(below, "q", 0, 1, hi_open=True) == below


def test_number_field_open_flags_do_not_open_the_other_end():
    si = strict_input()
    assert si.number_field(0, "q", 0, 1, hi_open=True) == 0
    assert si.number_field(1, "q", 0, 1, lo_open=True) == 1
    ApiError = api_error_class()
    with pytest.raises(ApiError):
        si.number_field(0, "q", 0, 1, lo_open=True, hi_open=True)
    with pytest.raises(ApiError):
        si.number_field(1, "q", 0, 1, lo_open=True, hi_open=True)
    assert si.number_field(0.5, "q", 0, 1, lo_open=True, hi_open=True) == 0.5


@pytest.mark.parametrize("value", [
    "0.1", "", "1", " 1", "NaN", "Infinity",
    True, False,
    None,
    [], [1], {}, {"v": 1},
    (1,),
], ids=repr)
def test_number_field_refuses_what_is_not_a_json_number(value):
    ApiError = api_error_class()
    with pytest.raises(ApiError) as exc_info:
        strict_input().number_field(value, "beta", 0, 1)
    assert_api_error(exc_info, "INVALID_FIELD", "beta")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")], ids=repr)
def test_number_field_refuses_non_finite_floats(value):
    ApiError = api_error_class()
    with pytest.raises(ApiError) as exc_info:
        strict_input().number_field(value, "beta", 0, 1)
    assert_api_error(exc_info, "INVALID_FIELD", "beta")


def test_number_field_refuses_non_finite_floats_even_when_the_range_is_unbounded():
    si = strict_input()
    ApiError = api_error_class()
    for value in (float("inf"), float("-inf"), float("nan")):
        with pytest.raises(ApiError) as exc_info:
            si.number_field(value, "lambda", -math.inf, math.inf)
        assert_api_error(exc_info, "INVALID_FIELD", "lambda")


def test_number_field_refuses_an_integer_too_large_for_a_float():
    si = strict_input()
    ApiError = api_error_class()
    for hi in (100, math.inf):
        with pytest.raises(ApiError) as exc_info:
            si.number_field(10 ** 400, "lambda", 0, hi)
        assert_api_error(exc_info, "INVALID_FIELD", "lambda")


@pytest.mark.parametrize("value", [-0.1, -1, 0.0099, 100.5, 101, 1e9, -1e9, -100])
def test_number_field_refuses_values_outside_the_range(value):
    ApiError = api_error_class()
    with pytest.raises(ApiError) as exc_info:
        strict_input().number_field(value, "factor", 0.01, 100)
    err = assert_api_error(exc_info, "INVALID_FIELD", "factor")
    assert "0.01" in err.message and "100" in err.message  # the range is named


def test_number_field_error_names_the_field_and_the_range_of_a_unit_interval():
    ApiError = api_error_class()
    with pytest.raises(ApiError) as exc_info:
        strict_input().number_field(1.5, "beta", 0, 1)
    err = assert_api_error(exc_info, "INVALID_FIELD", "beta")
    assert "0" in err.message and "1" in err.message


def test_number_field_error_names_the_range_for_a_wrong_type_too():
    ApiError = api_error_class()
    with pytest.raises(ApiError) as exc_info:
        strict_input().number_field("0.1", "factor", 0.01, 100)
    err = assert_api_error(exc_info, "INVALID_FIELD", "factor")
    assert "0.01" in err.message and "100" in err.message


@pytest.mark.parametrize("value", [-0.0, 0.0, 0, -0])
def test_number_field_returns_zero_as_positive_float_zero(value):
    result = strict_input().number_field(value, "q", -1, 1)
    assert isinstance(result, float)
    assert result == 0.0
    assert math.copysign(1.0, result) == 1.0


def test_number_field_negative_zero_at_a_closed_bound_is_positive_zero():
    result = strict_input().number_field(-0.0, "q", 0, 1)
    assert result == 0.0 and math.copysign(1.0, result) == 1.0


def test_number_field_returns_the_number_not_a_string_or_bool():
    result = strict_input().number_field(0.25, "q", 0, 1)
    assert result == 0.25 and not isinstance(result, bool)
    assert strict_input().number_field(7, "q", 0, 10) == 7


def test_wire_number_field_accepts_a_number(wire):
    response, payload = post(wire, "/number", b'{"v": 2.5}')
    assert response.status_code == 200
    assert payload == {"ok": True, "v": 2.5}


@pytest.mark.parametrize("raw", [
    b'{"v": "0.1"}', b'{"v": true}', b'{"v": null}', b'{}', b'{"v": [1]}',
    b'{"v": 101}', b'{"v": -0.1}', b'{"v": 0.001}',
])
def test_wire_number_field_invalid_field_envelope(wire, raw):
    response, payload = post(wire, "/number", raw)
    assert_envelope(response, payload, "INVALID_FIELD", "v")
    assert "0.01" in payload["error"]["message"] and "100" in payload["error"]["message"]


@pytest.mark.parametrize("raw", [b'{"v": NaN}', b'{"v": Infinity}', b'{"v": -Infinity}'])
def test_wire_tokens_are_invalid_json_not_invalid_field(wire, raw):
    response, payload = post(wire, "/number", raw)
    assert_envelope(response, payload, "INVALID_JSON")


@pytest.mark.parametrize("raw", [b'{"v": 0}', b'{"v": 1}', b'{"v": -0.0}'])
def test_wire_open_bounds_refuse_the_bound(wire, raw):
    response, payload = post(wire, "/open", raw)
    assert_envelope(response, payload, "INVALID_FIELD", "v")


def test_wire_open_bounds_accept_inside(wire):
    response, payload = post(wire, "/open", b'{"v": 0.5}')
    assert response.status_code == 200 and payload == {"ok": True, "v": 0.5}


# --------------------------------------------------------------------------
# validate_revision
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 1, 7, 10 ** 6])
def test_validate_revision_accepts_a_non_negative_int(value):
    result = strict_input().validate_revision(value, "revision")
    assert result == value
    assert type(result) is int


@pytest.mark.parametrize("value", [
    True, False, 1.0, 0.0, 1.5, -1, -10 ** 6, -0.0, "1", "", None,
    float("nan"), float("inf"), [1], {"r": 1},
], ids=repr)
def test_validate_revision_refuses_everything_else(value):
    ApiError = api_error_class()
    with pytest.raises(ApiError) as exc_info:
        strict_input().validate_revision(value, "documentSerial")
    assert_api_error(exc_info, "INVALID_FIELD", "documentSerial")


def test_wire_validate_revision(wire):
    response, payload = post(wire, "/revision", b'{"r": 12}')
    assert response.status_code == 200 and payload == {"ok": True, "r": 12}
    for raw in (b'{"r": true}', b'{"r": 1.0}', b'{"r": -1}', b'{"r": "1"}', b'{"r": null}', b'{}'):
        response, payload = post(wire, "/revision", raw)
        assert_envelope(response, payload, "INVALID_FIELD", "revision")


# --------------------------------------------------------------------------
# the module changes nothing else (FN-70: no route yet, provider untouched)
# --------------------------------------------------------------------------

_ISOLATION_SCRIPT = r"""
import json, sys
from fta_web.app import create_app

def snapshot():
    app = create_app()
    rules = sorted((r.rule, r.endpoint, tuple(sorted(r.methods or ()))) for r in app.url_map.iter_rules())
    modules = sorted({getattr(f, "__module__", "") for f in app.view_functions.values()})
    provider = type(app.json)
    return {
        "rules": rules,
        "view_modules": modules,
        "provider": provider.__module__ + "." + provider.__qualname__,
        "dumps": app.json.dumps({"a": float("nan"), "b": [float("inf")], "c": 1.5}),
        "sort_keys": app.json.sort_keys,
        "handlers": sorted(str(k) for k in app.error_handler_spec.get(None, {}).get(None, {})),
    }

before = snapshot()
import fta_web.strict_input  # noqa: F401
after = snapshot()
print(json.dumps({"before": before, "after": after, "imported": "fta_web.strict_input" in sys.modules}))
"""


def test_importing_strict_input_changes_neither_routes_nor_json_provider():
    proc = subprocess.run(
        [sys.executable, "-c", _ISOLATION_SCRIPT],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert result["imported"] is True
    assert result["after"] == result["before"]
    # No route may be provided by the module yet.
    assert not any("strict_input" in m for m in result["after"]["view_modules"])
    assert not any("strict_input" in str(rule) for rule in result["after"]["rules"])
    # The existing provider still writes strict JSON (NaN and Infinity as null).
    assert result["after"]["provider"].endswith("FiniteJSONProvider")
    assert "NaN" not in result["after"]["dumps"] and "Infinity" not in result["after"]["dumps"]


def test_strict_input_does_not_switch_the_app_json_provider_in_process():
    si = strict_input()  # noqa: F841 - imported on purpose
    from fta_web.app import FiniteJSONProvider, create_app

    app = create_app()
    assert type(app.json) is FiniteJSONProvider
    assert json.loads(app.json.dumps({"x": float("nan")})) == {"x": None}
    assert not any(
        "strict_input" in getattr(view, "__module__", "") for view in app.view_functions.values()
    )
